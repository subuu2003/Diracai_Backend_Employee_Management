from django.db import models


class SiteConfig(models.Model):
    """
    Singleton model — only one row ever exists (pk=1).
    Stores editable homepage/branding content.
    Video is uploaded directly to DigitalOcean Spaces via django-storages.
    """
    company_name = models.CharField(
        max_length=100,
        default="DiracAI",
        help_text="Company name shown in the top navbar logo."
    )
    hero_heading = models.CharField(
        max_length=200,
        default="Your Vision, Our",
        help_text="First part of the large hero headline."
    )
    hero_highlight = models.CharField(
        max_length=100,
        default="Technology",
        help_text="The gradient-coloured word in the hero headline."
    )
    hero_subheading = models.TextField(
        default="From Vision to Reality With AI-Driven IT Services",
        help_text="Descriptive line below the main headline."
    )
    hero_video = models.FileField(
        upload_to="hero-videos/",
        null=True,
        blank=True,
        help_text="Background video for the hero section. Stored in DigitalOcean Spaces."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def __str__(self):
        return f"SiteConfig — {self.company_name}"

    @classmethod
    def get_solo(cls):
        """Return the singleton instance, creating it if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class HeroVideo(models.Model):
    """
    Individual video for the hero slideshow.
    Videos are stored in DigitalOcean Spaces via django-storages.
    """
    MEDIA_VIDEO = 'video'
    MEDIA_IMAGE = 'image'
    MEDIA_CHOICES = [(MEDIA_VIDEO, 'Video'), (MEDIA_IMAGE, 'Image')]

    media_type = models.CharField(
        max_length=10, choices=MEDIA_CHOICES, default=MEDIA_VIDEO,
        help_text='Type of media: video or image.'
    )
    video = models.FileField(
        upload_to='hero-videos/', null=True, blank=True,
        help_text='Video file stored in DigitalOcean Spaces.'
    )
    image = models.FileField(
        upload_to='hero-images/', null=True, blank=True,
        help_text='Image file stored in DigitalOcean Spaces.'
    )
    title = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Optional label (shown in admin only).'
    )
    duration = models.PositiveIntegerField(
        default=8,
        help_text='Seconds this clip plays before switching to the next.'
    )
    is_selected = models.BooleanField(
        default=False,
        help_text='Include this video in the homepage slideshow.'
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text='Position in the slideshow (lower = earlier).'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'uploaded_at']
        verbose_name = 'Hero Video'
        verbose_name_plural = 'Hero Videos'

    def __str__(self):
        return self.title or f'Hero Video #{self.pk}'
