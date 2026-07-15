from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import login, authenticate,logout
from account.forms import RegistrationForm,RegistrationForm2, AccountAuthenticationForm, ContactForm, RegistrationFormNew
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from account.models import Account
import os
from django.core.files.storage import default_storage
from django.core.files.storage import FileSystemStorage
import json
import base64
from django.core import files
from django.conf import settings
from django.db import transaction

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
import json
import logging
from .models import TeamMember, Blog
from .serializers import TeamMemberSerializer, PublicBlogSerializer
from .models import Blog
from .serializers import PublicBlogSerializer
from rest_framework.permissions import AllowAny
from rest_framework import viewsets
from rest_framework import generics


logger = logging.getLogger(__name__)

from django.urls import reverse

TEMP_PROFILE_IMAGE_NAME = "temp_profile_image.png"


# account/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Blog
from .serializers import PublicBlogSerializer
from rest_framework.permissions import AllowAny
from rest_framework import viewsets

class LoginView(APIView):
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        user = authenticate(username=username, password=password)

        if user is not None:
            refresh = RefreshToken.for_user(user)

            # 🧩 Make sure to include phoneno & email if they exist
            response = Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": getattr(user, 'email', None),
                    "phoneno": getattr(user, 'phoneno', None),
                }
            }, status=status.HTTP_200_OK)
            response.set_cookie(
                "access_token",
                str(refresh.access_token),
                httponly=True,
                samesite="Lax",
                secure=request.is_secure(),
                path="/",
            )
            response.set_cookie(
                "refresh_token",
                str(refresh),
                httponly=True,
                samesite="Lax",
                secure=request.is_secure(),
                path="/",
            )
            return response
        else:
            return Response(
                {"detail": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )


from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from .models import TeamMember
from .serializers import TeamMemberSerializer
from rest_framework import viewsets, parsers
from .models import Blog
from .serializers import PublicBlogSerializer
from rest_framework.permissions import AllowAny
from rest_framework import viewsets

class TeamMemberViewSet(viewsets.ModelViewSet):
    queryset = TeamMember.objects.all()
    serializer_class = TeamMemberSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]
def getSessionId(request):
    return HttpResponse(request.user.id)
class BlogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/blogs/
    GET /api/blogs/<slug>/
    Only returns published blogs for public frontend
    """
    serializer_class = PublicBlogSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return Blog.objects.filter(status="published").order_by("-published_at", "-created_at")

def mail(request):
    send_mail('Registration successful!',"jdsd",'From <edresearch.in@gmail.com>',['bibhu.phy@gmail.com'])
    return HttpResponse('mail sent')


def alreadyAuthenticated(request):
    return render(request,'account/alreadyAthenticated.html')


def register_view(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated:
            redirectURL=settings.BASE_URL+'/account/alreadyauthenticated'
            return redirect(redirectURL)

        context = {}
        if request.POST:
                form = RegistrationForm(request.POST)
                if form.is_valid():
                        form.save()
                        firstname = form.cleaned_data.get('firstname').lower()
                        lastname = form.cleaned_data.get('lastname').lower()
                        username = form.cleaned_data.get('username')
                        email = form.cleaned_data.get('email').lower()
                        raw_password = form.cleaned_data.get('password1')
                        account = authenticate(email=email, password=raw_password)
                        html_message = render_to_string('account/mail_template.html')
                        plain_message = strip_tags(html_message)
                        send_mail('Registration successful!',plain_message,'From <edresearch.in@gmail.com>',[email],html_message=html_message)
                        #login(request, account)
                        #user.registrationid="123"
                        #registrationid = "ED293872"
                        totalusers = Account.objects.filter().count()
                        currentaccount = Account.objects.get(username=username)
                        regno=1000000 #int(user.id)
                        regid="EDR"+str(regno)
                        currentaccount.registrationid=regid
                        currentaccount.save()
                        os.system("mkdir static/userfiles/%s"%(regid))
                        destination = kwargs.get("next")
                        if destination:
                              return redirect(destination)
                        #registrationsuccess_view(request) 
                        redirectURL=settings.BASE_URL+'/account/registrationsuccess/';
                        return redirect(redirectURL)
                else:
                        context['registration_form'] = form
        else:
                form = RegistrationForm()
                context['registration_form'] = form
        return render(request, 'account/register.html', context)

@csrf_exempt
def contact_api_submission(request):
    """
    API endpoint for Next.js contact form submissions
    """
    if request.method == 'POST':
        try:
            # Parse JSON data from Next.js
            data = json.loads(request.body)
            
            # Extract form data
            first_name = data.get('firstName', '').strip()
            last_name = data.get('lastName', '').strip()
            email = data.get('email', '').strip()
            subject = data.get('subject', '').strip()
            message = data.get('message', '').strip()
            
            # Validate required fields
            if not first_name:
                return JsonResponse({
                    'error': 'First name is required'
                }, status=400)
                
            if not email:
                return JsonResponse({
                    'error': 'Email is required'
                }, status=400)
                
            if not message:
                return JsonResponse({
                    'error': 'Message is required'
                }, status=400)
            
            # Prepare email content
            full_name = f"{first_name} {last_name}".strip()
            email_subject = f"DiracAI Contact: {subject}" if subject else "New Contact Form Submission"
            
            # Plain text version
            text_message = f"""
                New Contact Form Submission - DiracAI Website
                
                Name: {full_name}
                Email: {email}
                Subject: {subject or 'Not specified'}
                
                Message:
                {message}
                
                This message was sent from the DiracAI website contact form.
                            """
            
            # HTML version
            safe_message = message.replace('\n', '<br>')

            html_message = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #245091;">New Contact Form Submission - DiracAI</h2>
                <div style="background: #f8fafc; padding: 20px; border-radius: 8px;">
                    <p><strong>Name:</strong> {full_name}</p>
                    <p><strong>Email:</strong> {email}</p>
                    <p><strong>Subject:</strong> {subject or 'Not specified'}</p>
                    <p><strong>Message:</strong></p>
                    <div style="background: white; padding: 15px; border-radius: 4px; border-left: 4px solid #245091;">
                        {safe_message}
                    </div>
                </div>
                <p style="color: #64748b; font-size: 12px; margin-top: 20px;">
                    This message was sent from the DiracAI website contact form.
                </p>
            </div>
            """
            
            # Send email
            send_mail(
                email_subject,
                text_message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.CONTACT_EMAIL],  # Your receiving email
                html_message=html_message,
                fail_silently=False,
            )
            
            # Log the submission
            logger.info(f"Contact form submitted by {full_name} ({email})")
            
            return JsonResponse({
                'message': 'Thank you for your message! We will get back to you soon.'
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            logger.error(f"Contact form error: {str(e)}")
            return JsonResponse({
                'error': 'Failed to send message. Please try again later.'
            }, status=500)
    
    return JsonResponse({
        'error': 'Method not allowed'
    }, status=405)

def registrationsuccess_view(request):
    return render(request,"account/successreg.html")


def login_view(request, *args, **kwargs):
    redirectURL=settings.BASE_URL+'/dashboard/general';
    return redirect(redirectURL)



def login_viewOld(request, *args, **kwargs):
        context = {}
        user = request.user
        if user.is_authenticated:
               redirectURL=settings.BASE_URL+'/dashboard/main';              
               return redirect(redirectURL)
                                                               
        destination = get_redirect_if_exists(request)
        #print("destination: " + str(destination))
        
        if request.POST:
                form = AccountAuthenticationForm(request.POST)
                if form.is_valid():
                        email = request.POST['email']
                        password = request.POST['password']
                        user = authenticate(email=email, password=password)
                        if user:
                                login(request, user)
                                if destination:
                                      return redirect(destination)
                                redirectURL=settings.BASE_URL+'/dashboard/main';  
                                return redirect(redirectURL)
                                                                                           
        else:
             form = AccountAuthenticationForm()
                                                                                                                                                       
        context['login_form'] = form

        return render(request, "account/login.html", context)


def get_redirect_if_exists(request):
	redirect = None
	if request.GET:
		if request.GET.get("next"):
			redirect = str(request.GET.get("next"))
	return redirect




def logout_view(request):
        logout(request)
        if request.method == "POST" or request.path.startswith("/api/"):
            response = JsonResponse({"detail": "Logged out"}, status=200)
        else:
            response = redirect("home")
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
        return response



def userprofile_view(request):
        user = request.user
        if user.is_authenticated:
            return render(request,'account/student_userarea_userprofile.html')
        else:
            return redirect('https://edresearch.co.in/account/login')


def requestnewpassword_view(request):
    return render(request,'account/password_reset_email.html')






def employeeregister_view(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated:
            redirectURL=settings.BASE_URL+'/account/alreadyauthenticated'
            return redirect(redirectURL)

        context = {}
        if request.POST:
                form = RegistrationFormNew(request.POST)
                if form.is_valid():
                        form.save()
                        firstname = form.cleaned_data.get('firstname').lower()
                        lastname = form.cleaned_data.get('lastname').lower()
                        username = form.cleaned_data.get('username')
                        email = form.cleaned_data.get('email').lower()
                        raw_password = form.cleaned_data.get('password1')
                        account = authenticate(email=email, password=raw_password)
                        html_message = render_to_string('account/mail_template.html')
                        plain_message = strip_tags(html_message)
                        send_mail('Registration successful!',plain_message,'From <edresearch.in@gmail.com>',[email],html_message=html_message)
                        #login(request, account)
                        #user.registrationid="123"
                        #registrationid = "ED293872"
                        totalusers = Account.objects.filter().count()
                        currentaccount = Account.objects.get(username=username)
                        regno=1000000 #int(user.id)
                        regid="EDR"+str(regno)
                        currentaccount.registrationid=regid
                        currentaccount.save()
                        os.system("mkdir static/userfiles/%s"%(regid))
                        destination = kwargs.get("next")
                        if destination:
                              return redirect(destination)
                        #registrationsuccess_view(request) 
                        redirectURL=settings.BASE_URL+'/account/registrationsuccess/';
                        return redirect(redirectURL)
                else:
                        context['registration_form'] = form
        else:
                form = RegistrationForm()
                context['registration_form'] = form
        return render(request, 'account/registeremployee.html', context)









def registration_view(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated:
            redirectURL=settings.BASE_URL+'/account/alreadyauthenticated'
            return redirect(redirectURL)
        #print ("posss")
        context = {}
        if request.POST:
                #print ("Post request")
                form = RegistrationFormNew(request.POST)
                if form.is_valid():
                        form.save()
                        #firstname = form.cleaned_data.get('firstname').lower()
                        #lastname = form.cleaned_data.get('lastname').lower()
                        username = form.cleaned_data.get('username')
                        email = form.cleaned_data.get('email').lower()
                        #raw_password = form.cleaned_data.get('password1')
                        #account = authenticate(email=email, password=raw_password)
                        #html_message = render_to_string('account/mail_template.html')
                        #plain_message = strip_tags(html_message)
                        #send_mail('Registration successful!',plain_message,'From <edresearch.in@gmail.com>',[email],html_message=html_message)
                        #totalusers = Account.objects.filter().count()
                        #currentaccount = Account.objects.get(username=username)
                        #regno=1000000 #int(user.id)
                        #regid="EDR"+str(regno)
                        #currentaccount.registrationid=regid
                        #currentaccount.save()
                        #os.system("mkdir static/userfiles/%s"%(regid))
                        #destination = kwargs.get("next")
                        if destination:
                              return redirect(destination)
                        #registrationsuccess_view(request) 
                        redirectURL=settings.BASE_URL+'/account/registrationsuccess/';
                        return redirect(redirectURL)
                else:
                        context['registration_formnew'] = form
        else:
                form = RegistrationFormNew()
                context['registration_formnew'] = form
        return render(request, 'account/registernew.html', context)









def contactus_view(request, *args, **kwargs):
      context = {}
      if request.POST:
          form = ContactForm(request.POST)
          if form.is_valid():
              form.save()
              #return HttpResponseRedirect(reverse('register_view'))
              destination = kwargs.get("next")
              if destination:
                  return redirect(destination)
              #redirectURL=settings.BASE_URL+'/account/registrationsuccess/';
              #return redirect(redirectURL)
              #return HttpResponseRedirect('/account/registrationsuccess/')
              redirectURL=settings.BASE_URL+'';
              return redirect(redirectURL)
          else:
              context['registration_form'] = form
      else:
          form = ContactForm()
          context['contact_form'] = form
      return render(request,'account/ContactForm.html',context)  


def contact_view(request, *args, **kwargs):
    return render(request,'account/ContactForm.html')





def registration2_view(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated:
            redirectURL=settings.BASE_URL+'/account/alreadyauthenticated'
            return redirect(redirectURL)

        context = {}
        if request.POST:
                form = RegistrationForm2(request.POST)
                if form.is_valid():
                        form.save()
                        #firstname = form.cleaned_data.get('firstname').lower()
                        #lastname = form.cleaned_data.get('lastname').lower()
                        username = form.cleaned_data.get('username')
                        #email = form.cleaned_data.get('email').lower()
                        #raw_password = form.cleaned_data.get('password1')
                        #account = authenticate(email=email, password=raw_password)
                        #html_message = render_to_string('account/mail_template.html')
                        #plain_message = strip_tags(html_message)
                        #send_mail('Registration successful!',plain_message,'From <edresearch.in@gmail.com>',[email],html_message=html_message)
                        #login(request, account)
                        #user.registrationid="123"
                        #registrationid = "ED293872"
                        #totalusers = Account.objects.filter().count()
                        #currentaccount = Account.objects.get(username=username)
                        #regno=1000000 #int(user.id)
                        #regid="EDR"+str(regno)
                        #currentaccount.registrationid=regid
                        #currentaccount.save()
                        #os.system("mkdir static/userfiles/%s"%(regid))
                        #destination = kwargs.get("next")
                        #if destination:
                        #      return redirect(destination)
                        #registrationsuccess_view(request) 
                        redirectURL=settings.BASE_URL+'/account/registrationsuccess/';
                        return redirect(redirectURL)
                else:
                        context['registration_form'] = form
        else:
                form = RegistrationForm2()
                context['registration_form'] = form
        return render(request, 'account/register2.html', context)





def sendotp_view(request):
    return render(request, 'account/register2.html')



def registrationdone_view(request):
    return render(request, 'account/registration_done.html')

class BlogListAPI(generics.ListAPIView):
    """
    GET /api/blogs/
    Returns only published blogs (safe for public frontend)
    """
    serializer_class = PublicBlogSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Blog.objects.filter(status="published").order_by("-published_at", "-created_at")


class BlogDetailAPI(generics.RetrieveAPIView):
    """
    GET /api/blogs/<slug>/
    Returns single published blog by slug
    """
    serializer_class = PublicBlogSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return Blog.objects.filter(status="published")

from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework.throttling import ScopedRateThrottle
from .models import Blog, BlogCategory, BlogComment
from .serializers import (
    BlogAdminSerializer,
    BlogCategorySerializer,
    BlogCommentSerializer,
    BlogCommentCreateSerializer,
    BlogCommentAdminSerializer,
)

class BlogAdminViewSet(viewsets.ModelViewSet):
    queryset = Blog.objects.all().order_by("-created_at")
    serializer_class = BlogAdminSerializer
    permission_classes = [IsAdminUser]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]


class BlogCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BlogCategory.objects.all().order_by("name")
    serializer_class = BlogCategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"


class BlogCategoryAdminViewSet(viewsets.ModelViewSet):
    queryset = BlogCategory.objects.all().order_by("name")
    serializer_class = BlogCategorySerializer
    permission_classes = [IsAdminUser]
    lookup_field = "slug"


class BlogCommentListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "blog_comments"

    def get_throttles(self):
        if self.request.method != "POST":
            return []
        return super().get_throttles()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BlogCommentCreateSerializer
        return BlogCommentSerializer

    def _get_blog(self):
        slug = self.kwargs.get("slug")
        return get_object_or_404(Blog, slug=slug, status="published")

    def get_queryset(self):
        queryset = Blog.objects.filter(status='published')
        
        # Optional: Filter by featured if needed
        featured_only = self.request.query_params.get('featured', None)
        if featured_only and featured_only.lower() in ['true', '1', 'yes']:
            queryset = queryset.filter(featured=True)
            
        return queryset.order_by('-published_at', '-created_at')

    def perform_create(self, serializer):
        blog = self._get_blog()
        user = self.request.user if getattr(self.request, "user", None) and self.request.user.is_authenticated else None
        ip = self.request.META.get("REMOTE_ADDR")
        with transaction.atomic():
            serializer.save(blog=blog, user=user, status="pending", ip_address=ip)


class BlogCommentAdminViewSet(viewsets.ModelViewSet):
    queryset = BlogComment.objects.all().select_related("blog", "user").order_by("-created_at")
    serializer_class = BlogCommentAdminSerializer
    permission_classes = [IsAdminUser]
    parser_classes = [parsers.JSONParser]
