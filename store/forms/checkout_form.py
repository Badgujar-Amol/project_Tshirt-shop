from django import forms
from store.models import Order

class CheckForm(forms.ModelForm):
    class Meta:
        model=Order
        fields = ['shipping_address' , 'phone' , 'payment_method']