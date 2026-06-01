from branches.models import Branch
from branches.models import BranchAdmin
from django.contrib import admin


@admin.register(Branch)
class BranchAdminModel(admin.ModelAdmin):
    list_display = ("name", "school", "city", "status")
    search_fields = ("name", "address", "city", "region")
    list_filter = ("status",)


@admin.register(BranchAdmin)
class BranchAdminUserModel(admin.ModelAdmin):
    list_display = ("user", "branch", "role_title", "status")
    search_fields = ("role_title",)
    list_filter = ("status", "last_login")
