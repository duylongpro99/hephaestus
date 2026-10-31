"""C7 Composer: Script + AudioManifest + ShotList -> RenderProps (architecture §7).

A pure function: the same inputs always give the same props, so it is unit-testable and the
render is reproducible. Moves to `studio/` with Remotion in build step 3.
"""

from factory.contracts import AudioManifest, Caption, RenderProps, Scene, Script, ShotList

WIDTH, HEIGHT, FPS = 1920, 1080, 30


def compose(script: Script, audio: AudioManifest, shots: ShotList) -> RenderProps:
    timing = {line.line_id: line for line in audio.lines}
    shot_of = {shot.segment_id: shot for shot in shots.shots}
    scenes = []
    for segment in script.segments:
        voiced = [timing[line.id] for line in segment.lines if line.id in timing]
        if not voiced:  # a segment with nothing spoken has no time on the audio track
            continue
        text = {line.id: line.text for line in segment.lines}
        start = voiced[0].start_s
        end = voiced[-1].start_s + voiced[-1].duration_s + voiced[-1].pause_after_s
        shot = shot_of[segment.id]
        scenes.append(Scene(
            segment_id=segment.id, template=shot.template, image_uri=shot.assets[0],
            start_s=start, duration_s=round(end - start, 4),
            captions=[Caption(line_id=a.line_id, text=text[a.line_id], start_s=a.start_s,
                              duration_s=round(a.duration_s + a.pause_after_s, 4)) for a in voiced],
        ))
    return RenderProps(episode_id=script.episode_id, width=WIDTH, height=HEIGHT, fps=FPS,
                       audio_uri=audio.master_uri, total_duration_s=audio.total_duration_s, scenes=scenes)
