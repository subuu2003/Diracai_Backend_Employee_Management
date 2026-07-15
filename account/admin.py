from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.paginator import Paginator

from .models import (
    Product,
    ProductGallery,
    Project,
    TeamMember,
    GalleryItem,
    Account,
    ITSolution,
    UserType,
    UserTitle,
    FutureCustomerContacts,
    Institute,
    DegreeName,
    DocumentCopy,
    MarkSheet,
    Certificate,
    EduDegree,
    Achievements,
    Address,
    Blog,
    ContactInquiry,
)
from django.core.mail import send_mail
from django.utils import timezone

# ---------------------------
# Product Gallery Inline
# ---------------------------
class ProductGalleryInline(admin.TabularInline):
    model = ProductGallery
    extra = 3
    fields = ['image']
    show_change_link = True


# ---------------------------
# Product Admin (ONLY ONCE)
# ---------------------------
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'status', 'featured', 'created_at')
    list_filter = ('category', 'status', 'featured')
    search_fields = ('name', 'description')
    ordering = ('-created_at',)

    inlines = [ProductGalleryInline]

    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'tagline', 'iconText', 'category', 'status', 'featured', 'sortOrder')
        }),
        ('Cover Image', {
            'fields': ('cover',)
        }),
        ('Descriptions', {
            'fields': ('description', 'fullDescription')
        }),
        ('Links', {
            'fields': ('liveUrl', 'demoUrl', 'documentationUrl')
        }),
        ('Structured Data', {
            'fields': (
                'features',
                'outcomes',
                'challenges',
                'technologies',
                'stats',
                'platforms',
                'integrations',
                'support',
            ),
            'classes': ('collapse',),
        }),
    )


# ---------------------------
# Product Gallery Admin
# ---------------------------
@admin.register(ProductGallery)
class ProductGalleryAdmin(admin.ModelAdmin):
    list_display = ('product', 'created_at')
    list_filter = ('product',)
    search_fields = ('product__name',)


# ---------------------------
# Other Admins (unchanged)
# ---------------------------
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'status', 'created_at')


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'status', 'joinDate')


@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'created_at')


class AccountAdmin(UserAdmin):
    list_display = ('email', 'username', 'is_staff', 'is_admin')
    readonly_fields = ('id', 'date_joined', 'last_login')


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "author_name", "published_at", "created_at")
    list_filter = ("status", "created_at", "published_at")
    search_fields = ("title", "excerpt", "content", "category", "author_name")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'email', 'subject', 'created_at', 'replied_at')
    search_fields = ('first_name', 'last_name', 'email', 'subject')
    list_filter = ('created_at',)
    readonly_fields = ('first_name', 'last_name', 'email', 'subject', 'message', 'created_at', 'replied_at')
    fieldsets = (
        ('Inquiry Details', {
            'fields': ('first_name', 'last_name', 'email', 'subject', 'message', 'created_at')
        }),
        ('Admin Reply', {
            'fields': ('admin_reply', 'replied_at'),
            'description': 'Type your reply here and click save. An email will be sent automatically to the user.'
        }),
    )

    def save_model(self, request, obj, form, change):
        # If admin_reply has changed and is not empty, send an email
        if 'admin_reply' in form.changed_data and obj.admin_reply:
            subject = f"Re: {obj.subject}"
            message = obj.admin_reply
            from_email = None # Uses DEFAULT_FROM_EMAIL from settings
            recipient_list = [obj.email]
            
            try:
                send_mail(subject, message, from_email, recipient_list)
                obj.replied_at = timezone.now()
            except Exception as e:
                # In production, you might want to use the messages framework to alert the admin of failure
                pass
                
        super().save_model(request, obj, form, change)

admin.site.register(Account, AccountAdmin)

admin.site.register(UserType)
admin.site.register(UserTitle)
admin.site.register(FutureCustomerContacts)
admin.site.register(Institute)
admin.site.register(DegreeName)
admin.site.register(DocumentCopy)
admin.site.register(MarkSheet)
admin.site.register(Certificate)
admin.site.register(EduDegree)
admin.site.register(Achievements)
admin.site.register(Address)
admin.site.register(ITSolution)
