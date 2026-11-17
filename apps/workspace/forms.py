from django import forms
from django.core.exceptions import ValidationError

from apps.workspace.models import Project


class ProjectForm(forms.ModelForm):
    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    class Meta:
        model = Project
        fields = ('name', 'description')
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        duplicates = Project.objects.filter(owner=self.owner, name=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError('You already have a project with this name.')
        return name
