from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os
import datetime
from django.contrib.postgres.fields import ArrayField
from django.db.models.signals import m2m_changed
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify
# from django.core.validators import URLValidator

#from django.contrib.auth import get_user_model
#User = get_user_model()


class Testimonial(models.Model):
    """Model for client testimonials"""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    name = models.CharField(max_length=200, help_text="Client's full name")
    company = models.CharField(max_length=200, help_text="Company name")
    role = models.CharField(max_length=200, help_text="Job title/role")
    text = models.TextField(help_text="Testimonial content")
    image = models.ImageField(
        upload_to='testimonials/',
        blank=True,
        null=True,
        help_text="Client's profile photo"
    )
    linkedin = models.URLField(
        max_length=500,
        blank=True,
        default="/#",
        help_text="LinkedIn profile URL (use /# if not available)"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    sort_order = models.IntegerField(
        default=0,
        help_text="Order in which testimonials appear (lower numbers first)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order', '-created_at']
        verbose_name = 'Testimonial'
        verbose_name_plural = 'Testimonials'
    
    def __str__(self):
        return f"{self.name} - {self.company}"

# IT Service Model (now also used for GIS services)
class Service(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    # Basic Information
    # `id` previously served as the slug/primary key; keep it but allow blank so
    # the `save` method can auto‑populate it from the title/slug field.
    id = models.CharField(max_length=50, primary_key=True, blank=True)

    # url-friendly slug is now stored separately so public endpoints can look
    # up by slug while leaving the primary key untouched for backwards
    # compatibility.  It will be generated from the title when blank.
    slug = models.SlugField(max_length=255, unique=True, blank=True, db_index=True)

    title = models.CharField(max_length=200)
    description = models.TextField()
    # icon_name = models.CharField(max_length=50, default="Code")  # e.g., "Code", "Brain"
    image = models.ImageField(upload_to='IT-services/', blank=True, null=True)
    
    # Detailed Information
    long_description = models.TextField(blank=True)
    features = models.JSONField(default=list, blank=True)  # List of strings
    benefits = models.JSONField(default=list, blank=True)  # List of strings
    technologies = models.JSONField(default=list, blank=True)  # List of strings
    use_cases = models.JSONField(default=list, blank=True)
    explore = models.JSONField(default=dict, blank=True)
    
    # Relations
    developers = models.ManyToManyField('TeamMember', blank=True, related_name='services')
    demo_video_url = models.URLField(blank=True, null=True)
    
    # Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        # generate slug if missing
        base_slug = slugify(self.slug or self.title or "")[:240]
        if not base_slug:
            base_slug = "service"

        slug_candidate = base_slug
        suffix = 2
        # avoid infinite loop on collisions
        while Service.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
            slug_candidate = f"{base_slug}-{suffix}"
            suffix += 1

        self.slug = slug_candidate

        # if id was not provided, default it to the slug (trimmed to 50 chars)
        if not self.id:
            self.id = self.slug[:50]

        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.title
    
    class Meta:
        ordering = ['sort_order', 'title']


class GisService(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    id = models.CharField(max_length=50, primary_key=True, blank=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, db_index=True)

    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to='GIS-services/', blank=True, null=True)

    long_description = models.TextField(blank=True)
    features = models.JSONField(default=list, blank=True)
    benefits = models.JSONField(default=list, blank=True)
    technologies = models.JSONField(default=list, blank=True)
    use_cases = models.JSONField(default=list, blank=True)
    explore = models.JSONField(default=dict, blank=True)

    developers = models.ManyToManyField('TeamMember', blank=True, related_name='gis_services')
    demo_video_url = models.URLField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        base_slug = slugify(self.slug or self.title or "")[:240]
        if not base_slug:
            base_slug = "gis-service"

        slug_candidate = base_slug
        suffix = 2
        while GisService.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
            slug_candidate = f"{base_slug}-{suffix}"
            suffix += 1

        self.slug = slug_candidate

        if not self.id:
            self.id = self.slug[:50]

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['sort_order', 'title']


class TeamMember(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Alumni', 'Alumni')
    ]
    
    MEMBER_TYPE_CHOICES = [
        ('founder', 'Founder'),
        ('executive', 'Executive Leadership'), 
        ('employee', 'Employee'),
        ('alumni', 'Alumni'),
    ]
    
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='team/', blank=True, null=True)
    bio = models.TextField(blank=True)
    
    # Keep both fields - they serve different purposes
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active')
    member_type = models.CharField(max_length=20, choices=MEMBER_TYPE_CHOICES, default='employee')
    
    # Optional fields for founders/executives
    education = models.TextField(blank=True, null=True)
    joinDate = models.DateField(blank=True, null=True)
    memberID = models.CharField(max_length=50, blank=True, null=True)
    linkedin_url = models.URLField(max_length=500, blank=True, null=True)
    skills = models.JSONField(blank=True, null=True, default=list)
    achievements = models.JSONField(blank=True, null=True, default=list)  # New field
    experience = models.TextField(blank=True, null=True)  # New field
    use_cases = models.JSONField(default=list, blank=True)  # New field to describe typical use cases for this team member's expertise
    
    def __str__(self):
        return self.name


from django.db import models
import json
from django.utils import timezone


class Project(models.Model):
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
    ]
    
    CATEGORY_CHOICES = [
        ('mobile', 'Mobile'),
        ('fintech', 'Fintech'),
        ('saas', 'SaaS'),
        ('edtech', 'Edtech'),
        ('ai', 'AI'),
        ('blockchain', 'Blockchain'),
        ('devops', 'DevOps'),
        ('ecommerce', 'Ecommerce'),
        ('govtech', 'Govtech'),
        ('enterprise', 'Enterprise'),
    ]
    
    # Existing fields
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=500, blank=True, default='mobile')
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    image = models.ImageField(upload_to='projects/', blank=True, null=True)
    image_url = models.URLField(blank=True)
    
    # CHANGED: Use camelCase for shortDescription
    shortDescription = models.CharField(max_length=200, blank=True)  # Changed from short_description
    client = models.CharField(max_length=200, blank=True)
    technologies = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    timeline = models.CharField(max_length=100, blank=True)
    team = models.CharField(max_length=200, blank=True)
    team_members = models.ManyToManyField(TeamMember, blank=True, related_name='projects')
    employee_team_members = models.ManyToManyField('account.EmployeeProfile', blank=True, related_name='projects')
    project_manager = models.ForeignKey('account.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_projects')
    working_days = models.JSONField(default=list, blank=True)
    spare_until = models.DateField(blank=True, null=True)
    rejoin_notes = models.TextField(blank=True)
    image_description = models.TextField(blank=True)
    work_goals = models.TextField(blank=True)
    goal_deadline = models.DateField(blank=True, null=True)
    color = models.CharField(max_length=100, default='from-blue-500 to-purple-600')
    featured = models.BooleanField(default=False)
    details = models.TextField(blank=True)
    challenges = models.JSONField(default=list, blank=True)
    outcomes = models.JSONField(default=list, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    gallery = models.JSONField(default=list, blank=True)
    icon = models.CharField(max_length=50, default='Briefcase')
    liveUrl = models.URLField(blank=True)  # Changed from live_url
    videoUrl = models.URLField(blank=True)  # Changed from video_url
    sortOrder = models.IntegerField(default=0, help_text="Order in which projects appear (lower numbers first)")
    
    # Testimonial fields
    testimonial_name = models.CharField(max_length=200, blank=True)
    testimonial_role = models.CharField(max_length=200, blank=True)
    testimonial_image = models.URLField(blank=True)
    testimonial_quote = models.TextField(blank=True)
    testimonial_rating = models.IntegerField(default=5)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['sortOrder', '-created_at']


class ProjectMembership(models.Model):
    ROLE_CHOICES = [
        ('viewer', 'Viewer'),
        ('member', 'Member'),
        ('lead', 'Lead'),
        ('pm', 'Project Manager'),
    ]

    project = models.ForeignKey('account.Project', on_delete=models.CASCADE, related_name='memberships')
    employee = models.ForeignKey('account.EmployeeProfile', on_delete=models.CASCADE, related_name='project_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('project', 'employee'),)
        indexes = [
            models.Index(fields=['project', 'is_active']),
            models.Index(fields=['employee', 'is_active']),
        ]
        ordering = ['-updated_at']


class GalleryItem(models.Model):
    CATEGORY_CHOICES = [
        ('office', 'Office'),
        ('events', 'Events'),
        ('celebration', 'Celebration'),
        ('others', 'Others'),
    ]
    
    title = models.CharField(max_length=150, blank=True)
    image = models.ImageField(upload_to='gallery/')
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES, 
        default='office'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title or "Gallery Item"

# Add this to your models.py after the GalleryItem model
class Product(models.Model):
    STATUS_CHOICES = [
        ('Live', 'Live'),
        ('In Development', 'In Development'),
        ('Coming Soon', 'Coming Soon'),
    ]
    
    CATEGORY_CHOICES = [
        ('education', 'Education'),
        ('business', 'Business'),
        ('productivity', 'Productivity'),
        ('analytics', 'Analytics'),
        ('communication', 'Communication'),
        ('development', 'Development'),
        ('design', 'Design'),
        ('marketing', 'Marketing'),
        ('finance', 'Finance'),
        ('healthcare', 'Healthcare'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=300)
    iconText = models.CharField(max_length=3, blank=True)  # Single character or short text
    cover = models.ImageField(upload_to='products/covers/', blank=True, null=True)
    
    # Description
    description = models.TextField(blank=True)
    fullDescription = models.TextField(blank=True)
    
    # Categorization
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='education')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='In Development')
    
    # Arrays/Lists
    features = models.JSONField(default=list, blank=True)
    outcomes = models.JSONField(default=list, blank=True)
    challenges = models.JSONField(default=list, blank=True)
    technologies = models.JSONField(default=list, blank=True)
    stats = models.JSONField(default=list, blank=True)  # Array of {label, value} objects
#     gallery = models.JSONField(default=list, blank=True)
    platforms = models.JSONField(default=list, blank=True)
    integrations = models.JSONField(default=list, blank=True)
    support = models.JSONField(default=list, blank=True)
    
    # URLs
    liveUrl = models.URLField(blank=True)
    demoUrl = models.URLField(blank=True)
    documentationUrl = models.URLField(blank=True)
    pricing = models.CharField(
    max_length=100,
    blank=True,
    null=True
    )

    # Settings
    featured = models.BooleanField(default=False)
    sortOrder = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['sortOrder', '-created_at']

class ProductGallery(models.Model):
    product = models.ForeignKey(Product, related_name='gallery_images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='products/gallery/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Product Galleries"

    def __str__(self):
        return f"Gallery image for {self.product.name}"

class MyAccountManagerAll(BaseUserManager):
      def create_user(self, username, email, phoneno, password=None):
        if not username and not email and not phoneno:
            raise ValueError("At least one of username, email, or phone number must be provided.")

        user = self.model(
            username=username,
            email=self.normalize_email(email) if email else None,
            phoneno=phoneno
        )
        user.set_password(password)
        user.save(using=self._db)
        return user
      def create_superuser(self,  username,email, phoneno, password):
                user = self.create_user(
                        email=self.normalize_email(email),
                        phoneno=phoneno,
                        password=password,
                        username=username,
                )
                user.is_admin = True
                user.is_staff = True
                user.is_superuser = True
                user.save(using=self._db)
                return user

class MyAccountManager(BaseUserManager):
	def create_user(self, email, username, password=None):
		if not email:
			raise ValueError('Users must have an email address')
		if not username:
			raise ValueError('Users must have a username')

		user = self.model(
			email=self.normalize_email(email),
			username=username,
		)

		user.set_password(password)
		user.save(using=self._db)
		return user

	def create_superuser(self, email, username, password):
		user = self.create_user(
			email=self.normalize_email(email),
			password=password,
			username=username,
		)
		user.is_admin = True
		user.is_staff = True
		user.is_superuser = True
		user.save(using=self._db)
		return user


class MyAccountManagerWEmail(BaseUserManager):
        def create_user(self, email, password=None):
                if not email:
                        raise ValueError('Users must have an email address')

                user = self.model(
                        email=self.normalize_email(email),
                        #username=username,
                )

                user.set_password(password)
                user.save(using=self._db)
                return user

        def create_superuser(self, email, password):
                user = self.create_user(
                        email=self.normalize_email(email),
                        password=password,
                        #username=username,
                )
                user.is_admin = True
                user.is_staff = True
                user.is_superuser = True
                user.save(using=self._db)
                return user





class MyAccountManagerWUsername(BaseUserManager):
        def create_user(self,  username ,password=None):
                if not username:
                        raise ValueError('Users must have a username')

                user = self.model(
                        username=username,
                )

                user.set_password(password)
                user.save(using=self._db)
                return user

        def create_superuser(self,  username, password=None):
                user = self.create_user(
                        #email=self.normalize_email(email),
                        password=password,
                        username=username,
                )
                user.is_admin = True
                user.is_staff = True
                user.is_superuser = True
                user.save(using=self._db)
                return user



def get_profile_image_filepath(self, filename):
	return 'profile_images/' + str(self.pk) + '/profile_image.png'

def get_default_profile_image():
	return "codingwithmitch/logo_1080_1080.png"

def get_default_institute_logo():
       return "codingwithmitch/instlogodefault.png"



class UserType(models.Model):
    name=models.CharField(max_length=50)
    def __str__(self):
        return self.name


class UserTitle(models.Model):
    name=models.CharField(max_length=25)
    def __str__(self):
        return self.name


class Institute(models.Model):
      dummyoptions = (('yes','YES'),('no','NO'),)
      name = models.CharField(max_length=300,null=True, blank=True);
      city = models.CharField(max_length=300,null=True, blank=True);
      state = models.CharField(max_length=300,null=True, blank=True);
      country = models.CharField(max_length=300,null=True, blank=True);
      instlogo = models.ImageField(max_length=255, upload_to='images/', null=True, blank=True, default=get_default_institute_logo);
      dummy  = models.CharField(max_length=10, choices=dummyoptions, default='no',null=True,blank=True) 
      #def __str__(self):
      #  return "hello"


                
class DegreeName(models.Model):
      name = models.CharField(max_length=300,null=True, blank=True);
      def __str__(self):
        return self.name



class DocumentCopy(models.Model):
      name = models.CharField(max_length=300);
      doc = models.FileField(max_length=255, upload_to='images/', null=True, blank=True);
      def __str__(self):
        return self.name



class MarkSheet(models.Model):
      name = models.CharField(max_length=300,null=True, blank=True);
      doc = models.FileField(max_length=255, upload_to='images/', null=True, blank=True);
      def __str__(self):
        return self.name


class Certificate(models.Model):
      name = models.CharField(max_length=300,null=True, blank=True);
      doc = models.FileField(max_length=255, upload_to='images/', null=True, blank=True);
      def __str__(self):
        return self.name





class EduDegree(models.Model):
      institute = models.ForeignKey(Institute, on_delete=models.CASCADE,null=True, default=None,blank=True);
      degreename = models.ForeignKey(DegreeName, on_delete=models.CASCADE,null=True, default=None,blank=True);
      startDate = models.DateField(default=datetime.date.today,null=True,blank=True);
      endDate = models.DateField(default=datetime.date.today,null=True,blank=True);
      marksheets = models.ManyToManyField(MarkSheet, blank=True,default=None);
      certificates = models.ManyToManyField(Certificate, blank=True, default=None);
      #def __str__(self):
      #  return self.degreename 

      class Meta:
        ordering = ('startDate',)


class Achievements(models.Model):
      name = models.CharField(max_length=300,null=True, blank=True);
      description = models.CharField(max_length=1000,null=True, blank=True);
      startDate = models.DateField(default=datetime.date.today,null=True,blank=True);
      endDate = models.DateField(default=datetime.date.today,null=True,blank=True);
      def __str__(self):
          return str(self.name)



class Address(models.Model):
      addOptions = (('present','PRESENT'),('permanent','PERMANENT'),)
      careof = models.CharField(max_length=200,null=True, blank=True);
      houseno = models.CharField(max_length=100,null=True, blank=True);
      streetno = models.CharField(max_length=200,null=True, blank=True);
      placename = models.CharField(max_length=200,null=True, blank=True);
      postoffice = models.CharField(max_length=200,null=True, blank=True);
      district = models.CharField(max_length=200,null=True, blank=True);
      policestn = models.CharField(max_length=200,null=True, blank=True);
      pincode = models.CharField(max_length=200,null=True, blank=True);
      city = models.CharField(max_length=200,null=True, blank=True);
      state = models.CharField(max_length=200,null=True, blank=True);
      country = models.CharField(max_length=200,null=True, blank=True);
      addressType  = models.CharField(max_length=50, choices=addOptions, default='present',null=True,blank=True);
      def __str__(self):
          return str(self.id)




class UsefullLink(models.Model):
      name = models.CharField(max_length=200, null=True,blank=True)
      link = models.CharField(max_length=1000, null=True,blank=True)
      description = models.CharField(max_length=500, null=True,blank=True)
      creationDateTime = models.DateTimeField(default=timezone.now)
      def __str__(self):
        return self.name
      class Meta:
        ordering = ('creationDateTime',)













class Account(AbstractBaseUser, PermissionsMixin):
    usertitle = models.ForeignKey(UserTitle, on_delete=models.CASCADE,null=True, default=None,blank=True)
    firstname = models.CharField(verbose_name="firstname", max_length=20, unique=False,default="",blank=True)
    lastname = models.CharField(verbose_name="lastname", max_length=20, unique=False,default="",blank=True)
    email = models.EmailField(verbose_name="email", max_length=60, null=True, default=None,blank=True)
    phoneno = models.CharField(max_length=20, unique=False, null=True, blank=True)
    username = models.CharField(max_length=200, unique=True)
    usertype = models.ForeignKey(UserType, on_delete=models.CASCADE,null=True, default=None)
    date_joined = models.DateTimeField(verbose_name='date joined', auto_now_add=True)
    last_login = models.DateTimeField(verbose_name='last login', auto_now=True)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    profile_image = models.ImageField(max_length=255, upload_to='images/', null=True, blank=True, default=get_default_profile_image);
    hide_email = models.BooleanField(default=True);
    registrationid = models.CharField(verbose_name="regid", max_length=60, unique=False,default="");
    gender = models.CharField(verbose_name="gender", max_length=20, unique=False,default="",blank=True); 
    position = models.CharField(verbose_name="position", max_length=20, unique=False,default="",blank=True);
    dateofbirth = models.DateField(verbose_name="dob",max_length=8,unique=False,default=datetime.date.today)
    institute = models.CharField(verbose_name="institute", max_length=20, unique=False,default="",blank=True);
    city = models.CharField(verbose_name="city", max_length=20, unique=False,default="",blank=True);
    state = models.CharField(verbose_name="state", max_length=20, unique=False,default="",blank=True);
    country = models.CharField(verbose_name="country", max_length=20, unique=False,default="",blank=True);
    officeId_doc = models.FileField(max_length=1055, upload_to='images/', null=True, blank=True);#, default=get_default_profile_image);
    govtId1_doc = models.FileField(max_length=1055, upload_to='images/', null=True, blank=True);#, default=get_default_profile_image);
    govtId2_doc = models.FileField(max_length=1055, upload_to='images/', null=True, blank=True);#, default=get_default_profile_image);
    dobCert_doc = models.FileField(max_length=1055, upload_to='images/', null=True, blank=True);#, default=get_default_profile_image);
    educationDegrees = models.ManyToManyField(EduDegree, blank=True);
    contacts = models.ManyToManyField("self", blank=True,symmetrical=False);
    addresses =  models.ManyToManyField(Address, blank=True);
    achievements = models.ManyToManyField(Achievements, blank=True);
    usefull_links = models.ManyToManyField(UsefullLink, blank=True);             



    USERNAME_FIELD = 'username';
    REQUIRED_FIELDS = ['email','phoneno'];
    objects = MyAccountManagerAll()
    def __str__(self):
       return self.username
    def get_profile_image_filename(self):
       return str(self.profile_image)[str(self.profile_image).index('profile_images/' + str(self.pk) + "/"):]
    # For checking permissions. to keep it simple all admin have ALL permissons
    def has_perm(self, perm, obj=None):
       return self.is_admin
    # Does this user have permission to view this app? (ALWAYS YES FOR SIMPLICITY)
    def has_module_perms(self, app_label):
       return True



class FutureCustomerContacts(models.Model):
    name = models.CharField(max_length=100);
    email = models.CharField(max_length=100);
    subject = models.CharField(max_length=100);
    message = models.CharField(max_length=1000);
    postdate = models.DateField(default=datetime.date.today);
    def __str__(self):
        return self.name




class Subscribers(models.Model):
     email = models.CharField(max_length=100);
     postdate = models.DateField(default=datetime.date.today);


class Blog(models.Model):
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("published", "Published"),
    )

    # Core content
    title = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        db_index=True
    )
    excerpt = models.TextField(blank=True)
    content = models.TextField()

    # Classification
    category = models.CharField(max_length=100, blank=True, default="")
    tags = models.JSONField(default=list, blank=True)

    # Media
    banner_image = models.ImageField(upload_to="blogs/banners/", blank=True, null=True)
    banner_image_url = models.URLField(blank=True, max_length=2000)

    # Author (simple & frontend-compatible)
    author_name = models.CharField(max_length=120, blank=True, default="")
    author_avatar = models.ImageField(upload_to="blogs/authors/", blank=True, null=True)
    author_avatar_url = models.URLField(blank=True, max_length=2000)
    author_role = models.CharField(max_length=120, blank=True)

    # Publishing
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft"
    )
    featured = models.BooleanField(default=False)

    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    canonical_url = models.CharField(max_length=255, blank=True)
    allow_indexing = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def save(self, *args, **kwargs):
        base_slug = slugify(self.slug or self.title or "")[:240]
        if not base_slug:
            base_slug = "blog"

        slug_candidate = base_slug
        suffix = 2
        while Blog.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
            slug_candidate = f"{base_slug}-{suffix}"
            suffix += 1

        self.slug = slug_candidate
        if self.status == "published" and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class BlogCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        base_slug = slugify(self.slug or self.name or "")[:130]
        if not base_slug:
            base_slug = "category"

        slug_candidate = base_slug
        suffix = 2
        while BlogCategory.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
            slug_candidate = f"{base_slug}-{suffix}"
            suffix += 1

        self.slug = slug_candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BlogComment(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("spam", "Spam"),
    )

    blog = models.ForeignKey(Blog, related_name="comments", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.blog_id}:{self.name}"


from .employee_models import EmployeeProfile, OTPVerification, LeaveRequest, OvertimeRequest, EmployeeDocument


