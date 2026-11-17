"""Versioned calculator-specific request contracts over shared price inputs."""
from decimal import Decimal, InvalidOperation


def _decimal(value, field, *, minimum=Decimal('0')):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f'{field} must be a decimal-safe value.')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{field} must be a valid decimal value.')
    if not result.is_finite() or result < minimum:
        raise ValueError(f'{field} must be at least {minimum}.')
    return result


def validate_talking_flyer_contract(value):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('talking_flyer must use schema_version 1.')
    script = value.get('script', '')
    if not isinstance(script, str):
        raise ValueError('Talking Flyer script must be text.')
    try:
        if isinstance(value.get('word_count'), bool) or isinstance(value.get('narration_wpm'), bool):
            raise ValueError
        word_count = int(value.get('word_count'))
        wpm = int(value.get('narration_wpm'))
    except (TypeError, ValueError):
        raise ValueError('Talking Flyer word_count and narration_wpm must be integers.')
    if word_count < 0 or not 60 <= wpm <= 240:
        raise ValueError('Talking Flyer word_count must be non-negative and narration_wpm must be 60–240.')
    narration_duration = _decimal(value.get('narration_duration_seconds'), 'narration_duration_seconds')
    plan = value.get('clip_plan')
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise ValueError('Talking Flyer clip_plan must use schema_version 1.')
    clips = plan.get('clips')
    if not isinstance(clips, list) or not clips or len(clips) > 100:
        raise ValueError('Talking Flyer clip_plan.clips must contain 1–100 clips.')
    normalized, sequences = [], set()
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict):
            raise ValueError(f'clip_plan.clips[{index}] must be an object.')
        try:
            if isinstance(clip.get('sequence'), bool) or isinstance(clip.get('word_count'), bool):
                raise ValueError
            sequence = int(clip.get('sequence'))
            words = int(clip.get('word_count'))
        except (TypeError, ValueError):
            raise ValueError(f'clip_plan.clips[{index}] sequence and word_count must be integers.')
        if sequence < 1 or sequence in sequences or words < 0:
            raise ValueError(f'clip_plan.clips[{index}] has an invalid sequence or word_count.')
        sequences.add(sequence)
        duration = _decimal(clip.get('duration_seconds'), f'clip_plan.clips[{index}].duration_seconds', minimum=Decimal('0.001'))
        reserved = _decimal(clip.get('reserved_duration_seconds', '0'), f'clip_plan.clips[{index}].reserved_duration_seconds')
        usable = _decimal(clip.get('usable_duration_seconds', duration - reserved), f'clip_plan.clips[{index}].usable_duration_seconds')
        if reserved >= duration or usable != duration - reserved:
            raise ValueError(f'clip_plan.clips[{index}] usable duration must equal generated duration minus reserved duration.')
        text = clip.get('text', '')
        if not isinstance(text, str):
            raise ValueError(f'clip_plan.clips[{index}].text must be text.')
        normalized.append({'sequence': sequence, 'duration_seconds': str(duration), 'word_count': words,
            'text': text, 'reserved_duration_seconds': str(reserved), 'usable_duration_seconds': str(usable),
            'billing_assumptions': clip.get('billing_assumptions', {})})
    normalized.sort(key=lambda item: item['sequence'])
    if [item['sequence'] for item in normalized] != list(range(1, len(normalized) + 1)):
        raise ValueError('Talking Flyer clip sequences must be consecutive and start at 1.')
    total_generated = sum((Decimal(item['duration_seconds']) for item in normalized), Decimal('0'))
    total_reserved = sum((Decimal(item['reserved_duration_seconds']) for item in normalized), Decimal('0'))
    total_usable = sum((Decimal(item['usable_duration_seconds']) for item in normalized), Decimal('0'))
    if sum(item['word_count'] for item in normalized) != word_count:
        raise ValueError('Talking Flyer clip word counts must sum to the script word_count.')
    if 'clip_count' in plan and int(plan['clip_count']) != len(normalized):
        raise ValueError('Talking Flyer clip_count must match the supplied clip list.')
    if 'total_planned_generated_duration_seconds' in plan and _decimal(plan['total_planned_generated_duration_seconds'], 'total_planned_generated_duration_seconds') != total_generated:
        raise ValueError('Total planned generated duration must equal the sum of clip durations.')
    if 'total_reserved_duration_seconds' in plan and _decimal(plan['total_reserved_duration_seconds'], 'total_reserved_duration_seconds') != total_reserved:
        raise ValueError('Total reserved duration must equal the sum of clip reserved durations.')
    if 'total_usable_duration_seconds' in plan and _decimal(plan['total_usable_duration_seconds'], 'total_usable_duration_seconds') != total_usable:
        raise ValueError('Total usable duration must equal the sum of clip usable durations.')
    if script and word_count != len(script.split()):
        raise ValueError('Talking Flyer word_count must match the supplied script.')
    return {'schema_version': 1, 'script': script, 'word_count': word_count, 'narration_wpm': wpm,
        'narration_duration_seconds': str(narration_duration), 'clip_plan': {'schema_version': 1,
            'clip_count': len(normalized), 'clips': normalized,
            'total_planned_generated_duration_seconds': str(total_generated),
            'total_reserved_duration_seconds': str(total_reserved), 'total_usable_duration_seconds': str(total_usable),
            'billing_assumptions': plan.get('billing_assumptions', {})}}


def validate_video_generation_contract(value, raw_tools):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('video_generation must use schema_version 1.')
    brief = value.get('video_brief', '')
    if not isinstance(brief, str) or not brief.strip() or len(brief) > 4000:
        raise ValueError('video_generation.video_brief must be 1–4000 characters.')
    def text_field(key, limit, required=False):
        result = value.get(key, '')
        if not isinstance(result, str) or len(result) > limit or (required and not result.strip()):
            qualifier = ' and must not be empty' if required else ''
            raise ValueError(f'The field video_generation.{key} must be text of at most {limit} characters{qualifier}.')
        return result

    title = text_field('title', 160)
    purpose = text_field('purpose', 500)
    target_audience = text_field('target_audience', 500)
    destination_platform = text_field('destination_platform', 160)
    aspect_ratio = text_field('aspect_ratio', 80)
    output_resolution = text_field('output_resolution', 80)
    visual_style = text_field('visual_style', 1000)
    production_instructions = text_field('production_instructions', 2000)
    tone = text_field('tone', 500)
    narrative_direction = text_field('narrative_direction', 1000)
    script_directions = text_field('script_directions', 4000)
    method = value.get('script_preparation_method')
    if method not in ('self_written', 'ai_assisted'):
        raise ValueError('script_preparation_method must be self_written or ai_assisted.')
    script = value.get('script', '')
    if not isinstance(script, str) or not script.strip() or len(script) > 50000:
        raise ValueError('Video Generation script must contain 1–50,000 characters.')
    tool_id = value.get('scriptwriting_tool_id')
    selected_tool_ids = {str(item.get('tool_id')) for item in raw_tools if isinstance(item, dict)}
    if method == 'self_written' and tool_id:
        raise ValueError('Self-written scripts cannot select an AI scriptwriting tool.')
    if method == 'ai_assisted' and (not tool_id or str(tool_id) not in selected_tool_ids):
        raise ValueError('AI-assisted script preparation must select its priced scriptwriting tool.')
    scenes = value.get('scenes', [])
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 100:
        raise ValueError('video_generation.scenes must contain 1–100 scenes.')
    normalized_scenes, seen = [], set()
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ValueError(f'video_generation.scenes[{index}] must be an object.')
        try:
            if isinstance(scene.get('sequence'), bool):
                raise ValueError
            sequence = int(scene.get('sequence'))
        except (TypeError, ValueError):
            raise ValueError(f'video_generation.scenes[{index}].sequence must be an integer.')
        def scene_text(key, limit, default=''):
            result = scene.get(key, default)
            if not isinstance(result, str) or len(result) > limit:
                raise ValueError(f'video_generation.scenes[{index}].{key} must be text of at most {limit} characters.')
            return result
        description = scene_text('description', 2000)
        if sequence < 1 or sequence in seen or not description.strip():
            raise ValueError(f'video_generation.scenes[{index}] has an invalid sequence or description.')
        seen.add(sequence)
        duration = scene.get('planned_duration_seconds')
        if duration in (None, ''):
            raise ValueError(f'video_generation.scenes[{index}].planned_duration_seconds is required.')
        normalized_scenes.append({'sequence': sequence, 'title': scene_text('title', 180),
            'description': description, 'visual_direction': scene_text('visual_direction', 2000),
            'camera_direction': scene_text('camera_direction', 500), 'generation_prompt': scene_text('generation_prompt', 4000),
            'planned_duration_seconds': str(_decimal(duration, f'video_generation.scenes[{index}].planned_duration_seconds', minimum=Decimal('0.001'))) if duration is not None else None,
            'required_visual_assets': scene_text('required_visual_assets', 1000),
            'required_voice_audio': scene_text('required_voice_audio', 1000),
            'production_notes': scene_text('production_notes', 1000)})
    if seen and seen != set(range(1, len(seen) + 1)):
        raise ValueError('Video Generation scene sequences must be consecutive and start at 1.')
    normalized_scenes.sort(key=lambda item: item['sequence'])
    planned_duration = sum((_decimal(item['planned_duration_seconds'], 'scene duration') for item in normalized_scenes if item['planned_duration_seconds'] is not None), Decimal('0'))
    target_duration = value.get('target_finished_duration_seconds')
    if target_duration in (None, ''):
        raise ValueError('video_generation.target_finished_duration_seconds is required.')
    return {'schema_version': 1, 'title': title, 'video_brief': brief, 'purpose': purpose,
        'target_audience': target_audience, 'destination_platform': destination_platform,
        'aspect_ratio': aspect_ratio, 'output_resolution': output_resolution,
        'visual_style': visual_style, 'production_instructions': production_instructions,
        'tone': tone, 'narrative_direction': narrative_direction, 'script_preparation_method': method,
        'script_directions': script_directions, 'script': script,
        'scriptwriting_tool_id': str(tool_id) if tool_id else None, 'scenes': normalized_scenes,
        'target_finished_duration_seconds': str(_decimal(target_duration, 'target_finished_duration_seconds', minimum=Decimal('0.001'))),
        'total_planned_scene_duration_seconds': str(planned_duration)}
