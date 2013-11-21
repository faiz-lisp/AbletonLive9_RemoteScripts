#Embedded file name: /Users/versonator/Jenkins/live/Projects/AppLive/Resources/MIDI Remote Scripts/Push/SessionRecordingComponent.py
from functools import partial
from _Framework.SubjectSlot import subject_slot
from _Framework.CompoundComponent import CompoundComponent
from _Framework.Util import forward_property, find_if, index_if
from _Framework import Task
from _Framework.ToggleComponent import ToggleComponent
from ActionWithOptionsComponent import ToggleWithOptionsComponent
from consts import MessageBoxText
from MessageBoxComponent import Messenger
import Live
_Q = Live.Song.Quantization
LAUNCH_QUANTIZATION = (_Q.q_quarter,
 _Q.q_half,
 _Q.q_bar,
 _Q.q_2_bars,
 _Q.q_4_bars,
 _Q.q_8_bars,
 _Q.q_8_bars,
 _Q.q_8_bars)
LENGTH_OPTION_NAMES = ('1 Beat', '2 Beats', '1 Bar', '2 Bars', '4 Bars', '8 Bars', '16 Bars', '32 Bars')
LENGTH_LABELS = ('Recording length:', '', '', '')

def track_fired_slot(track):
    index = track.fired_slot_index
    if index >= 0:
        return track.clip_slots[index]


def track_playing_slot(track):
    index = track.playing_slot_index
    if index >= 0:
        return track.clip_slots[index]


def track_is_recording(track):
    playing_slot = track_playing_slot(track)
    return playing_slot and playing_slot.is_recording


def track_will_record(track):
    fired_slot = track_fired_slot(track)
    return fired_slot and fired_slot.will_record_on_start


def track_can_overdub(track):
    return not track.has_audio_input


def song_selected_slot(song):
    view = song.view
    scene = view.selected_scene
    track = view.selected_track
    scene_index = list(song.scenes).index(scene)
    try:
        slot = track.clip_slots[scene_index]
    except IndexError:
        slot = None

    return slot


class SessionRecordingComponent(CompoundComponent, Messenger):
    """
    Orchestrates the session recording (clip slot based) workflow.
    """

    def __init__(self, clip_creator = None, view_controller = None, *a, **k):
        super(SessionRecordingComponent, self).__init__(*a, **k)
        raise clip_creator or AssertionError
        raise view_controller or AssertionError
        self._target_slots = []
        self._clip_creator = clip_creator
        self._view_controller = view_controller
        self._new_button = None
        self._scene_list_new_button = None
        self._record_button = None
        self._length_press_state = None
        self._new_scene_button = None
        self._fixed_length = self.register_component(ToggleWithOptionsComponent())
        self._length_selector = self._fixed_length.options
        self._length_selector.option_names = LENGTH_OPTION_NAMES
        self._length_selector.selected_option = 3
        self._length_selector.labels = LENGTH_LABELS
        self._on_selected_fixed_length_option_changed.subject = self._length_selector
        length, _ = self._get_selected_length()
        self._clip_creator.fixed_length = length
        song = self.song()
        self._automation_toggle, self._re_enable_automation_toggle, self._delete_automation = self.register_components(ToggleComponent('session_automation_record', song), ToggleComponent('re_enable_automation_enabled', song, read_only=True), ToggleComponent('has_envelopes', None, read_only=True))
        self._on_tracks_changed_in_live.subject = song
        self._on_is_playing_changed_in_live.subject = song
        self._track_subject_slots = self.register_slot_manager()
        self._reconnect_track_listeners()
        self.register_slot(song, self.update, 'overdub')
        self.register_slot(song, self.update, 'session_record_status')
        self.register_slot(song.view, self.update, 'selected_track')
        self.register_slot(song.view, self.update, 'selected_scene')
        self.register_slot(song.view, self.update, 'detail_clip')

    length_layer = forward_property('_length_selector')('layer')

    def set_record_button(self, button):
        self._record_button = button
        self._on_record_button_value.subject = button
        self._update_record_button()

    def set_automation_button(self, button):
        self._automation_toggle.set_toggle_button(button)

    def set_re_enable_automation_button(self, button):
        self._re_enable_automation_toggle.set_toggle_button(button)
        self._on_re_enable_automation_value.subject = button

    def set_delete_automation_button(self, button):
        self._delete_automation.set_toggle_button(button)
        self._on_delete_automation_value.subject = button

    def set_scene_list_new_button(self, button):
        self._scene_list_new_button = button
        self._on_scene_list_new_button_value.subject = button
        self._update_scene_list_new_button()

    def set_new_button(self, button):
        self._new_button = button
        self._on_new_button_value.subject = button
        self._update_new_button()

    def set_length_button(self, button):
        self._fixed_length.set_action_button(button)
        self._on_length_value.subject = button
        self._length_press_state = None

    def set_new_scene_button(self, button):
        self._new_scene_button = button
        self._on_new_scene_button_value.subject = button
        self._update_new_scene_button()

    def deactivate_recording(self):
        self._stop_recording()

    def update(self):
        if self.is_enabled():
            self._delete_automation.subject = self._get_playing_clip()
            self._update_record_button()
            self._update_new_button()
            self._update_scene_list_new_button()
            self._update_new_scene_button()

    def _update_scene_list_new_button(self):
        self._update_generic_new_button(self._scene_list_new_button)

    def _update_new_button(self):
        self._update_generic_new_button(self._new_button)

    def _update_generic_new_button(self, new_button):
        if new_button and self.is_enabled():
            song = self.song()
            selected_track = song.view.selected_track
            clip_slot = song.view.highlighted_clip_slot
            can_new = clip_slot != None and clip_slot.clip or selected_track.can_be_armed and selected_track.playing_slot_index >= 0
            new_button.set_light(new_button.is_pressed() if can_new else 'DefaultButton.Disabled')

    def _update_new_scene_button(self):
        if self._new_scene_button and self.is_enabled():
            song = self.song()
            track_is_playing = find_if(lambda x: x.playing_slot_index >= 0, song.tracks)
            can_new = not song.view.selected_scene.is_empty or track_is_playing
            self._new_scene_button.set_light(self._new_scene_button.is_pressed() if can_new else 'DefaultButton.Disabled')

    def _update_record_button(self):
        if self._record_button and self.is_enabled():
            song = self.song()
            status = song.session_record_status
            if status == Live.Song.SessionRecordStatus.transition:
                self._record_button.set_light('Recording.Transition')
            elif status == Live.Song.SessionRecordStatus.on or song.session_record:
                self._record_button.turn_on()
            else:
                self._record_button.turn_off()

    @subject_slot('value')
    def _on_re_enable_automation_value(self, value):
        if self.is_enabled() and value:
            self.song().re_enable_automation()

    @subject_slot('value')
    def _on_delete_automation_value(self, value):
        if self.is_enabled() and value:
            clip = self._get_playing_clip()
            if clip:
                clip.clear_all_envelopes()

    def _get_playing_clip(self):
        playing_clip = None
        selected_track = self.song().view.selected_track
        try:
            playing_slot_index = selected_track.playing_slot_index
            if playing_slot_index >= 0:
                playing_clip = selected_track.clip_slots[playing_slot_index].clip
        except RuntimeError:
            pass

        return playing_clip

    @subject_slot('tracks')
    def _on_tracks_changed_in_live(self):
        self._reconnect_track_listeners()

    @subject_slot('is_playing')
    def _on_is_playing_changed_in_live(self):
        if self.is_enabled():
            self._update_record_button()

    @subject_slot('value')
    def _on_record_button_value(self, value):
        if self.is_enabled() and value:
            if not self._stop_recording():
                self._start_recording()

    @subject_slot('value')
    def _on_new_scene_button_value(self, value):
        if self.is_enabled() and value and self._prepare_new_action():
            song = self.song()
            selected_scene_index = list(song.scenes).index(song.view.selected_scene)
            try:
                self._create_silent_scene(selected_scene_index)
            except Live.Base.LimitationError:
                self.expect_dialog(MessageBoxText.SCENE_LIMIT_REACHED)

    @subject_slot('value')
    def _on_scene_list_new_button_value(self, value):
        if self.is_enabled() and value and self._prepare_new_action():
            song = self.song()
            view = song.view
            try:
                if view.highlighted_clip_slot.clip != None:
                    song.capture_and_insert_scene(Live.Song.CaptureMode.all_except_selected)
                else:
                    view.selected_track.stop_all_clips(False)
            except Live.Base.LimitationError:
                self.expect_dialog(MessageBoxText.SCENE_LIMIT_REACHED)

            self._view_selected_clip_detail()

    @subject_slot('value')
    def _on_new_button_value(self, value):
        if self.is_enabled() and value and self._prepare_new_action():
            song = self.song()
            view = song.view
            try:
                selected_track = view.selected_track
                selected_scene_index = list(song.scenes).index(view.selected_scene)
                selected_track.stop_all_clips(False)
                self._jump_to_next_slot(selected_track, selected_scene_index)
            except Live.Base.LimitationError:
                self.expect_dialog(MessageBoxText.SCENE_LIMIT_REACHED)

            self._view_selected_clip_detail()

    def _prepare_new_action(self):
        song = self.song()
        selected_track = song.view.selected_track
        if selected_track.can_be_armed:
            song.overdub = False
            return True

    def _has_clip(self, scene_or_track):
        return find_if(lambda x: x.clip != None, scene_or_track.clip_slots) != None

    def _create_silent_scene(self, scene_index):
        song = self.song()
        song.stop_all_clips(False)
        selected_scene = song.view.selected_scene
        if not selected_scene.is_empty:
            new_scene_index = list(song.scenes).index(selected_scene) + 1
            song.view.selected_scene = song.create_scene(new_scene_index)

    def _jump_to_next_slot(self, track, start_index):
        song = self.song()
        new_scene_index = self._next_empty_slot(track, start_index)
        song.view.selected_scene = song.scenes[new_scene_index]

    def _stop_recording(self):
        """ Retriggers all new recordings and returns true if there
        was any recording at all """
        song = self.song()
        status = song.session_record_status
        if not status != Live.Song.SessionRecordStatus.off:
            was_recording = song.session_record
            song.session_record = was_recording and False
        return was_recording

    def _start_recording(self):
        song = self.song()
        song.overdub = True
        selected_scene = song.view.selected_scene
        scene_index = list(song.scenes).index(selected_scene)
        track = song.view.selected_track
        if track.can_be_armed and (track.arm or track.implicit_arm):
            self._record_in_slot(track, scene_index)
        if not song.is_playing:
            song.is_playing = True

    def _find_last_clip(self):
        """ Finds the last clip of the session and returns the scene index """
        scenes = self.song().scenes
        return len(scenes) - index_if(self._has_clip, reversed(scenes)) - 1

    def _next_empty_slot(self, track, scene_index):
        """ Finds an empty slot in the track after the given position,
        creating new scenes if needed, and returns the found scene
        index """
        song = self.song()
        scene_count = len(song.scenes)
        while track.clip_slots[scene_index].has_clip:
            scene_index += 1
            if scene_index == scene_count:
                song.create_scene(scene_count)

        return scene_index

    def _record_in_slot(self, track, scene_index):
        song = self.song()
        clip_slot = track.clip_slots[scene_index]
        if self._fixed_length.is_active and not clip_slot.has_clip:
            length, quant = self._get_selected_length()
            if track_can_overdub(track):
                self._clip_creator.create(clip_slot, length)
            else:
                clip_slot.fire(record_length=length, launch_quantization=quant)
        elif not clip_slot.is_playing:
            if clip_slot.has_clip:
                clip_slot.fire(force_legato=True, launch_quantization=_Q.q_no_q)
            else:
                clip_slot.fire()
        if song.view.selected_track == track:
            song.view.selected_scene = song.scenes[scene_index]
        self._view_selected_clip_detail()

    @subject_slot('value')
    def _on_length_value(self, value):
        if value:
            self._on_length_press()
        else:
            self._on_length_release()

    @subject_slot('selected_option')
    def _on_selected_fixed_length_option_changed(self, _):
        length, _ = self._get_selected_length()
        self._clip_creator.fixed_length = length

    def _on_length_press(self):
        song = self.song()
        slot = song_selected_slot(song)
        if slot == None:
            return
        clip = slot.clip
        if slot.is_recording and not clip.is_overdubbing:
            self._length_press_state = (slot, clip.playing_position)

    def _on_length_release(self):
        song = self.song()
        slot = song_selected_slot(song)
        if slot == None:
            return
        clip = slot.clip
        if self._length_press_state is not None:
            press_slot, press_position = self._length_press_state
            if press_slot == slot and self._fixed_length.is_active and slot.is_recording and not clip.is_overdubbing:
                length, _ = self._get_selected_length()
                one_bar = 4.0 * song.signature_numerator / song.signature_denominator
                loop_end = int(press_position / one_bar) * one_bar
                loop_start = loop_end - length
                if loop_start >= 0.0:
                    clip.loop_end = loop_end
                    clip.end_marker = loop_end
                    clip.loop_start = loop_start
                    clip.start_marker = loop_start
                    self._tasks.add(Task.sequence(Task.delay(0), Task.run(partial(slot.fire, force_legato=True, launch_quantization=_Q.q_no_q))))
                    self.song().overdub = False
                self._fixed_length.is_active = False
        self._length_press_state = None

    def _get_selected_length(self):
        song = self.song()
        length = 2.0 ** self._length_selector.selected_option
        quant = LAUNCH_QUANTIZATION[self._length_selector.selected_option]
        if self._length_selector.selected_option > 1:
            length = length * song.signature_numerator / song.signature_denominator
        return (length, quant)

    def _view_selected_clip_detail(self):
        view = self.song().view
        if view.highlighted_clip_slot.clip:
            view.detail_clip = view.highlighted_clip_slot.clip
        self._view_controller.show_view('Detail/Clip')

    def _reconnect_track_listeners(self):
        manager = self._track_subject_slots
        manager.disconnect()
        for track in self.song().tracks:
            if track.can_be_armed:
                manager.register_slot(track, self.update, 'arm')
                manager.register_slot(track, self.update, 'playing_slot_index')
                manager.register_slot(track, self.update, 'fired_slot_index')

    def _set_scene_list_mode(self, scene_list_mode):
        self._scene_list_mode = scene_list_mode
        self._update_new_button()

    def _get_scene_list_mode(self):
        return self._scene_list_mode

    scene_list_mode = property(_get_scene_list_mode, _set_scene_list_mode)