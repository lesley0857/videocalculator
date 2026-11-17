from django.db import migrations


WORKFLOWS = [
    ('Text to video', 'text-to-video', 'Generate video from a text prompt.'),
    ('Image to video', 'image-to-video', 'Generate or animate video from image input.'),
    ('Video to video', 'video-to-video', 'Transform or continue an existing video.'),
    ('Native talking avatar or video', 'native-talking-avatar', 'Generate a talking avatar/video with native speech or dialogue.'),
    ('Avatar with external narration or audio', 'avatar-external-audio', 'Generate an avatar video using externally prepared narration or audio.'),
    ('External text-to-speech and lip sync', 'external-tts-lip-sync', 'Combine external speech synthesis with a lip-sync step.'),
    ('Image or avatar animation', 'image-avatar-animation', 'Animate an image or avatar.'),
    ('Other video workflow', 'other', 'Extensible category for a workflow not listed above.'),
]


def seed_workflows(apps, schema_editor):
    Workflow = apps.get_model('video_registry', 'Workflow')
    for name, slug, description in WORKFLOWS:
        Workflow.objects.get_or_create(slug=slug, defaults={'name': name, 'description': description})


def remove_seeded_workflows(apps, schema_editor):
    # Workflows may already be referenced or edited in the database. Preserve them on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [('video_registry', '0002_capabilityrevision')]
    operations = [migrations.RunPython(seed_workflows, remove_seeded_workflows)]
