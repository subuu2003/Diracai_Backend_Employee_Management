from django.shortcuts import render

# Create your views here.


from django.shortcuts import render,HttpResponse, redirect
# Create your views here.
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages

from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.core.mail import send_mail
from django.views.generic import TemplateView
from django.views.decorators.cache import never_cache
from django.conf import settings
from django.http import HttpResponseNotFound
from django.template import TemplateDoesNotExist
from pathlib import Path



from django.http import HttpResponseRedirect
#reactapp=never_cache(TemplateView.as_view(template_name="index.html"))

def reactapp(request):
        try:
            return render(request, "index.html")
        except TemplateDoesNotExist:
            base_dir = Path(getattr(settings, "BASE_DIR", Path(__file__).resolve().parent.parent))
            for candidate in (base_dir / "build" / "index.html", base_dir / "public" / "index.html"):
                if candidate.exists():
                    content = candidate.read_text(encoding="utf-8", errors="ignore")
                    if "%PUBLIC_URL%" in content:
                        content = content.replace("%PUBLIC_URL%", "")
                    return HttpResponse(content)
            return HttpResponseNotFound("index.html not found")



def reactappPar(request,pk):
    return reactapp(request)


def reactappPkGk(request,gk, pk):
    return reactapp(request)



def reactappvideomeet(request,meetingroomstring):
    return reactapp(request)


#        user = request.user
#        if user.is_authenticated:
#            return render(request,'index.html')
#        else:
#            redirectURL=settings.BASE_URL+'/account/login';
#            return redirect(redirectURL)





def index(request):
    return render(request, 'djangoIndex.html')


def newindex(request,  *args, **kwargs):
    return render(request, 'djangoIndex1.html')
    #return HttpResponseNotFound(" Page not found ")





def newindexteam(request):
    return render(request, 'djangoIndex1Team.html')











def privacypolicy(request):
    return render(request, 'privacypolicy.html')


def joinus(request):
    return render(request,'joinus.html') 

def joinusscienceanalystI(request):
    return render(request,'scienceanalystI.html')

def joinusscienceanalystII(request):
        return render(request,'scienceanalystII.html')



def bibhutiparida(request):
    return render(request,'BibhutiParida.html');

def rasmitasahoo(request):
    return render(request,'RasmitaSahoo.html');

def bibhuprasadmahakud(request):
    return render(request,'BibhuprasadMahakud.html');

def ipsitpanda(request):
    return render(request,'IpsitPanda.html');


def jackysingla(request):
    return render(request,'JackySingla.html');

def reetasingla(request):
    return render(request,'ReetaSingla.html');


def kiran(request):
    return render(request,'Kiran.html');



def debaprasadmahakud(request):
    return render(request,'DebaprasadMahakud.html');


def demoteacher(request):
    return render(request,'DemoTeacher.html');


def demostudent(request):
    return render(request,'DemoStudent.html');


def demomanager(request):
    return render(request,'DemoManager.html');


def demoinstitute(request):
    return render(request,'DemoInstitute.html');

def careeredr(request):
    return render(request,'CarrerEDResearch.html');


def applyjob(request):
    return redirect('https://docs.google.com/forms/d/e/1FAIpQLSfNsVaYUiI9uG3wicTVmPAA_8L2VeGHMnAlp5cDmKxH0Dps3A/viewform');








# ─── Site Configuration API ───────────────────────────────────────────────────
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from .models import SiteConfig
from .serializers import SiteConfigSerializer


class SiteConfigPublicView(APIView):
    """
    GET /api/site-config/
    Public - returns current config + hero video CDN URL.
    Used by the Next.js homepage on every load.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        config = SiteConfig.get_solo()
        serializer = SiteConfigSerializer(config, context={"request": request})
        return Response(serializer.data)


class SiteConfigAdminView(APIView):
    """
    PATCH /api/site-config/update/
    Admin-only - updates any field including uploading a new hero video
    (multipart/form-data). Video is written to DigitalOcean Spaces.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def patch(self, request):
        # Require is_staff (matches the project admin pattern)
        if not (request.user.is_staff or request.user.is_superuser or getattr(request.user, 'is_admin', False)):
            return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        config = SiteConfig.get_solo()
        serializer = SiteConfigSerializer(
            config,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        if serializer.is_valid():
            serializer.save()
            read_serializer = SiteConfigSerializer(
                SiteConfig.get_solo(), context={"request": request}
            )
            return Response(read_serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):
        return self.patch(request)

# ─── Hero Video API ────────────────────────────────────────────────────────────
from .models import HeroVideo
from .serializers import HeroVideoSerializer


class HeroVideoListCreateView(APIView):
    """
    GET  /api/hero-videos/          — public list (used by admin + homepage)
    POST /api/hero-videos/          — admin: upload a new video
    Query params:
      ?selected=true  → only return is_selected=True videos (for homepage)
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = HeroVideo.objects.all()
        if request.query_params.get('selected') == 'true':
            qs = qs.filter(is_selected=True)
        qs = qs.order_by('order', 'uploaded_at')
        serializer = HeroVideoSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser or getattr(request.user, 'is_admin', False)):
            return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)

        # Build a plain dict from non-file fields to avoid deepcopy of file handles
        # (request.data.copy() on a multipart QueryDict tries to deepcopy BufferedRandom
        #  file objects, which raises "cannot pickle '_io.BufferedRandom' object")
        data = {key: request.data[key] for key in request.data if key not in request.FILES}

        # Merge uploaded files into the data dict
        for key, f in request.FILES.items():
            data[key] = f

        # Auto-detect media_type from the uploaded file MIME type
        uploaded_file = request.FILES.get('video') or request.FILES.get('image') or request.FILES.get('file')
        if uploaded_file:
            mime = getattr(uploaded_file, 'content_type', '') or ''
            if mime.startswith('image/'):
                data['media_type'] = 'image'
                # Normalise: always store under the 'image' key
                if 'image' not in request.FILES:
                    data['image'] = uploaded_file
                    data.pop('video', None)
                    data.pop('file', None)
            else:
                data['media_type'] = 'video'

        serializer = HeroVideoSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            read_s = HeroVideoSerializer(
                HeroVideo.objects.get(pk=serializer.data['id']),
                context={'request': request}
            )
            return Response(read_s.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HeroVideoDetailView(APIView):
    """
    PATCH  /api/hero-videos/<id>/  — update title/duration/is_selected/order
    DELETE /api/hero-videos/<id>/  — remove video from library
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAuthenticated]

    def _get_object(self, pk):
        try:
            return HeroVideo.objects.get(pk=pk)
        except HeroVideo.DoesNotExist:
            return None

    def _check_admin(self, request):
        return request.user.is_staff or request.user.is_superuser or getattr(request.user, 'is_admin', False)

    def patch(self, request, pk):
        if not self._check_admin(request):
            return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = HeroVideoSerializer(obj, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            read_s = HeroVideoSerializer(HeroVideo.objects.get(pk=pk), context={'request': request})
            return Response(read_s.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if not self._check_admin(request):
            return Response({'detail': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # Delete file from storage too
        if obj.video:
            try:
                obj.video.delete(save=False)
            except Exception:
                pass
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
