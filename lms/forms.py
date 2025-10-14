from django import forms

class QuizForm(forms.Form):
    def __init__(self, *args, quiz=None, **kwargs):
        super().__init__(*args, **kwargs)
        if quiz is None:
            return
        for q in quiz.questions.all():
            field_name = f"q_{q.id}"
            choices = [(c.id, c.text) for c in q.choices.all()]
            self.fields[field_name] = forms.ChoiceField(
                label=q.text, choices=choices, widget=forms.RadioSelect
            )
