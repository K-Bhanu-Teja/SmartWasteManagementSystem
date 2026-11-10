from django import forms
from django.utils import timezone

from .models import Dustbin, Request


class UnifiedRequestForm(forms.ModelForm):
    class Meta:
        model = Request
        fields = (
            "title",
            "cause",
            "description",
            "photo",
            "latitude",
            "longitude",
            "address",
            "preferred_pickup_date",
            "preferred_pickup_time",
            "waste_category",
        )
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Brief title of the issue or request"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Describe the location, issue, or waste specifics"}),
            "latitude": forms.NumberInput(attrs={"step": "any", "id": "id_latitude"}),
            "longitude": forms.NumberInput(attrs={"step": "any", "id": "id_longitude"}),
            "address": forms.TextInput(attrs={"placeholder": "Street or landmark"}),
            "preferred_pickup_date": forms.DateInput(attrs={"type": "date"}),
            "preferred_pickup_time": forms.TimeInput(attrs={"type": "time"}),
            "waste_category": forms.Select(choices=[
                ("", "Select waste category"),
                ("Household", "Household"),
                ("Recyclable", "Recyclable"),
                ("Garden", "Garden"),
                ("Bulky", "Bulky waste"),
                ("Other", "Other"),
            ]),
        }

    def clean(self):
        cleaned_data = super().clean()
        cause = cleaned_data.get("cause")
        if cause == Request.Cause.SCHEDULED_WASTE_PICKUP:
            pickup_date = cleaned_data.get("preferred_pickup_date")
            if not pickup_date:
                self.add_error("preferred_pickup_date", "Please specify a preferred pickup date for scheduled pickups.")
            elif pickup_date < timezone.localdate():
                self.add_error("preferred_pickup_date", "Pickup date must be today or in the future.")
        return cleaned_data


class DustbinForm(forms.ModelForm):
    class Meta:
        model = Dustbin
        fields = ("name", "description", "latitude", "longitude", "last_cleaned_at", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. DBno1"}),
            "description": forms.TextInput(attrs={"placeholder": "Location description"}),
            "latitude": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 16.833944", "id": "id_dustbin_lat"}),
            "longitude": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 81.531444", "id": "id_dustbin_lng"}),
            "last_cleaned_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        lat = cleaned_data.get("latitude")
        lng = cleaned_data.get("longitude")
        if lat is not None and (lat < -90 or lat > 90):
            self.add_error("latitude", "Latitude must be between -90 and 90 degrees.")
        if lng is not None and (lng < -180 or lng > 180):
            self.add_error("longitude", "Longitude must be between -180 and 180 degrees.")
        return cleaned_data
