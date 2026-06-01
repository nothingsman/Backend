from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django.contrib.auth import forms as admin_forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import User


class _UserAdminEmailValidationMixin:
    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            return email

        conflict = User.objects.by_email(email)
        if self.instance.pk:
            conflict = conflict.exclude(pk=self.instance.pk)
        if conflict.exists():
            raise ValidationError(_("This email has already been taken."))
        return email


class UserAdminChangeForm(_UserAdminEmailValidationMixin, admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):
        model = User


class UserAdminCreationForm(
    _UserAdminEmailValidationMixin,
    admin_forms.UserCreationForm,
):
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):
        model = User
        fields = ("email",)
        error_messages = {
            "email": {"unique": _("This email has already been taken.")},
        }


class UserSignupForm(SignupForm):
    """
    Form rendered for standard account signup.
    """


class UserSocialSignupForm(SocialSignupForm):
    """
    Form rendered for social account signup.
    """
