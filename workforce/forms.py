from django import forms
from accounts.models import User, WorkerProfile
from citizen_services.models import Dustbin
from .models import Crew, Task, Vehicle, VehicleAssignment


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ("registration_number", "vehicle_type", "is_available")
        widgets = {
            "registration_number": forms.TextInput(attrs={"placeholder": "e.g. AP39 ZZ 9101"}),
            "vehicle_type": forms.TextInput(attrs={"placeholder": "e.g. Compactor, Mini Tipper"}),
        }


class VehicleAssignmentForm(forms.Form):
    vehicle = forms.ModelChoiceField(
        queryset=Vehicle.objects.filter(is_available=True),
        label="Select Vehicle",
    )
    driver = forms.ModelChoiceField(
        queryset=User.objects.filter(role=User.Role.WORKER, worker_profile__designation=WorkerProfile.Designation.DRIVER),
        label="Select Driver",
    )


class TaskCreationForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = (
            "title",
            "category",
            "description",
            "dustbin",
            "latitude",
            "longitude",
            "location_name",
            "due_date",
            "assigned_worker",
            "assigned_crew",
        )
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Task Title"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Task details and instructions"}),
            "latitude": forms.NumberInput(attrs={"step": "any"}),
            "longitude": forms.NumberInput(attrs={"step": "any"}),
            "location_name": forms.TextInput(attrs={"placeholder": "Area, street, or landmark"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dustbin"].required = False
        self.fields["assigned_worker"].required = False
        self.fields["assigned_crew"].required = False
        self.fields["assigned_worker"].queryset = User.objects.filter(role=User.Role.WORKER)
        self.fields["assigned_crew"].queryset = Crew.objects.filter(is_active=True)
        self.fields["dustbin"].queryset = Dustbin.objects.filter(is_active=True)


    def clean(self):
        cleaned_data = super().clean()
        lat = cleaned_data.get("latitude")
        lng = cleaned_data.get("longitude")
        if lat is not None and (lat < -90 or lat > 90):
            self.add_error("latitude", "Latitude must be between -90 and 90 degrees.")
        if lng is not None and (lng < -180 or lng > 180):
            self.add_error("longitude", "Longitude must be between -180 and 180 degrees.")
        return cleaned_data


class TaskCompletionForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("completion_photo", "completion_remarks")
        widgets = {
            "completion_remarks": forms.Textarea(attrs={"rows": 3, "placeholder": "Enter completion remarks (required)", "required": "required"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["completion_photo"].required = True
        self.fields["completion_remarks"].required = True
