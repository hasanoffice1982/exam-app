from django import forms

from . import marking


class MarksUploadForm(forms.Form):
    responses = forms.FileField(label="Google Forms responses (.csv)")
    roll_column = forms.CharField(required=False, label="Roll number column", help_text="Leave blank to detect")
    score_column = forms.CharField(required=False, label="Score column", help_text="Leave blank to detect")

    def clean_responses(self):
        upload = self.cleaned_data["responses"]
        if not upload.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file.")
        try:
            return marking.read_responses(upload.read(marking.MAX_UPLOAD_BYTES + 1))
        except marking.MarkingError as e:
            raise forms.ValidationError(str(e))
