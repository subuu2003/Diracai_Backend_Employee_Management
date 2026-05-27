import json
from typing import cast
from urllib import request
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename
import uuid
from django.conf import settings
from django.utils import timezone
from django.db.models import Q
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from .models import Service, GisService, TeamMember, Project, ProjectMembership, GalleryItem, Product, ProductGallery, Testimonial
from .serializers import ServiceSerializer, GisServiceSerializer, TeamMemberSerializer, ProjectSerializer, ProjectListSerializer, ProjectMembershipSerializer, GalleryItemSerializer, ProductSerializer, ProductGallerySerializer, TestimonialSerializer
from account.authentication import QuietJWTAuthentication
from account.employee_models import EmployeeProfile, CurrentProjectPlan
from account.employee_serializers import CurrentProjectPlanSerializer, PrivateProjectPlanSerializer
from account.pagination import DefaultPageNumberPagination, wants_pagination

class DebugForce200Mixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if not getattr(settings, "DEBUG", False):
            return response
        status_code = getattr(response, "status_code", 200)
        if status_code < 400:
            return response
        if hasattr(response, "data"):
            payload = response.data
            response.data = {
                "success": False,
                "original_status": int(status_code),
                "error": payload,
            }
        response.status_code = status.HTTP_200_OK
        return response



class ImageUploadAPI(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get("image") or request.FILES.get("file")
        if not file:
            return Response({"error": "No image provided"}, status=status.HTTP_400_BAD_REQUEST)

        filename = get_valid_filename(file.name)
        saved_path = default_storage.save(
            f"uploads/{uuid.uuid4().hex}-{filename}", file
        )
        url = default_storage.url(saved_path)
        absolute_url = request.build_absolute_uri(url)

        return Response(
            {
                "url": absolute_url,
                "image_url": absolute_url,
                "path": url,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminImageUploadAPI(ImageUploadAPI):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request and self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(
            {"detail": "Use POST to upload an image."},
            status=status.HTTP_200_OK,
        )


class TestimonialAPI(APIView):
    """
    API endpoint for testimonials
    GET: List all active testimonials
    POST: Create new testimonial (admin only)
    """
    
    def get(self, request):
        """Get all active testimonials ordered by sort_order"""
        try:
            testimonials = Testimonial.objects.filter(status='active').order_by('sort_order', '-created_at')
            serializer = TestimonialSerializer(testimonials, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request):
        """Create a new testimonial"""
        # Add authentication check here if needed
        # if not request.user.is_staff:
        #     return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = TestimonialSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TestimonialDetailAPI(APIView):
    """
    API endpoint for individual testimonial
    GET: Retrieve single testimonial
    PUT/PATCH: Update testimonial
    DELETE: Delete testimonial
    """
    
    def get_object(self, pk):
        """Helper method to get testimonial by ID"""
        try:
            return Testimonial.objects.get(pk=pk)
        except Testimonial.DoesNotExist:
            return None
    
    def get(self, request, pk):
        """Get single testimonial"""
        testimonial = self.get_object(pk)
        if not testimonial:
            return Response(
                {'error': 'Testimonial not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = TestimonialSerializer(testimonial)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):
        """Update testimonial (full update)"""
        testimonial = self.get_object(pk)
        if not testimonial:
            return Response(
                {'error': 'Testimonial not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = TestimonialSerializer(testimonial, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, pk):
        """Update testimonial (partial update)"""
        testimonial = self.get_object(pk)
        if not testimonial:
            return Response(
                {'error': 'Testimonial not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = TestimonialSerializer(testimonial, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        """Delete testimonial"""
        testimonial = self.get_object(pk)
        if not testimonial:
            return Response(
                {'error': 'Testimonial not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        testimonial.delete()
        return Response(
            {'message': 'Testimonial deleted successfully'},
            status=status.HTTP_204_NO_CONTENT
        )


class AdminDashboardAPI(APIView):
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        
        return Response({
            "msg": "ok", 
            "user": {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
                "phoneno": request.user.phoneno,
            }
        })

    def delete(self, request, pk=None):
        if pk is None:
            return Response({"detail": "Team member id is required"}, status=status.HTTP_400_BAD_REQUEST)
        member = TeamMember.objects.get(id=pk)
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# ------------------ SERVICE API ------------------
class ServiceAPI(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAuthenticated()]
    
    def get(self, request, pk=None):
        queryset = Service.objects.prefetch_related('developers')
        
        # lookup by id (primary key) when pk supplied
        if pk:
            # try pk first, then slug as fallback
            try:
                service = queryset.get(pk=pk)
            except Service.DoesNotExist:
                try:
                    service = queryset.get(slug=pk)
                except Service.DoesNotExist:
                    return Response({'error': 'Service not found'}, status=404)
            serializer = ServiceSerializer(service)
            return Response(serializer.data)
        
        # LIST view; behaviour differs for authenticated admin vs public
        if request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            # admin wants full list; allow optional status filter
            services = queryset.all()
            status_param = request.query_params.get('status')
            if status_param:
                services = services.filter(status=status_param)
        else:
            # public listing - default to active and support ?status and ?exclude
            services = queryset
            status_param = request.query_params.get('status', 'active')
            if status_param:
                services = services.filter(status=status_param)
            exclude = request.query_params.get('exclude')
            if exclude:
                services = services.exclude(id=exclude)
        
        serializer = ServiceSerializer(services, many=True)
        return Response(serializer.data)
    
    def post(self, request, pk=None):
        if pk is not None:
            return Response({"detail": "Method \"POST\" not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return self._save_service(request)
    
    def put(self, request, pk=None):
        try:
            service = Service.objects.get(pk=pk)
        except Service.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)
        return self._save_service(request, instance=service)
    
    def delete(self, request, pk=None):
        try:
            service = Service.objects.get(pk=pk)
            service.delete()
            return Response(status=204)
        except Service.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)
    
    def _save_service(self, request, instance=None):
        """
        Save service with proper list field handling
        """
        print("=== DEBUG START ===")
        print("1. Raw developers:", request.data.get('developers'))
        print("2. Type of developers:", type(request.data.get('developers')))
        print("3. getlist developers:", request.data.getlist('developers') if hasattr(request.data, 'getlist') else 'No getlist')

        # FIX: Create a mutable copy of request.data
        mutable_data = request.data.copy()

        print("4. mutable_data['developers']:", mutable_data.get('developers'))
        print("5. Type in mutable_data:", type(mutable_data.get('developers')))

        # Process developers first
        developer_ids = []

        # Get developers from request
        if hasattr(request.data, 'getlist') and request.data.getlist('developers'):
            # If sent as multiple form values
            dev_list = request.data.getlist('developers')
            print("5a. Got developers from getlist:", dev_list)
            for dev_item in dev_list:
                if isinstance(dev_item, str):
                    # Could be JSON string like "[1,2]"
                    if dev_item.startswith('[') and dev_item.endswith(']'):
                        try:
                            parsed = json.loads(dev_item)
                            if isinstance(parsed, list):
                                for item in parsed:
                                    try:
                                        developer_ids.append(int(item))
                                    except (ValueError, TypeError):
                                        continue
                        except json.JSONDecodeError:
                            # Try comma-separated
                            for id_str in dev_item.strip('[]').split(','):
                                try:
                                    developer_ids.append(int(id_str.strip()))
                                except ValueError:
                                    continue
                    else:
                        # Single ID
                        try:
                            developer_ids.append(int(dev_item))
                        except ValueError:
                            continue
                elif isinstance(dev_item, (int, float)):
                    developer_ids.append(int(dev_item))
        elif 'developers' in request.data:
            # If sent as single value
            dev_value = request.data['developers']
            print("5b. Got developers from single value:", dev_value)

            if isinstance(dev_value, str):
                if dev_value.strip() == '[]' or dev_value.strip() == '':
                    developer_ids = []
                else:
                    # Could be JSON string
                    try:
                        parsed = json.loads(dev_value)
                        if isinstance(parsed, list):
                            for item in parsed:
                                try:
                                    developer_ids.append(int(item))
                                except (ValueError, TypeError):
                                    continue
                    except json.JSONDecodeError:
                        # Try comma-separated
                        for id_str in dev_value.split(','):
                            try:
                                developer_ids.append(int(id_str.strip()))
                            except ValueError:
                                continue
            elif isinstance(dev_value, list):
                for item in dev_value:
                    try:
                        developer_ids.append(int(item))
                    except (ValueError, TypeError):
                        continue
                    
        print("6. Final developer_ids:", developer_ids)

        # Remove developers from mutable_data and handle separately
        if 'developers' in mutable_data:
            del mutable_data['developers']

        # Handle list fields like ProductAPI does
        list_fields = ['features', 'benefits', 'technologies']

        use_cases_value = None
        if 'use_cases' in mutable_data:
            raw_use_cases = mutable_data.get('use_cases')
            if isinstance(raw_use_cases, str):
                try:
                    parsed = json.loads(raw_use_cases)
                    use_cases_value = parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    use_cases_value = []
            elif isinstance(raw_use_cases, list):
                use_cases_value = raw_use_cases

        data = {}
        for key in mutable_data:
            if key in list_fields or key == 'use_cases':
                continue
            data[key] = mutable_data.get(key)

        # Process list fields
        for field in list_fields:
            if field in mutable_data:
                value = mutable_data[field]
                if isinstance(value, str):
                    try:
                        # Try to parse as JSON first
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            data[field] = [str(item).strip() for item in parsed if str(item).strip()]
                        else:
                            # Handle comma or newline separated
                            items = []
                            for line in value.split('\n'):
                                items.extend([item.strip() for item in line.split(',') if item.strip()])
                            data[field] = items
                    except json.JSONDecodeError:
                        # Handle comma or newline separated
                        items = []
                        for line in value.split('\n'):
                            items.extend([item.strip() for item in line.split(',') if item.strip()])
                        data[field] = items
                elif isinstance(value, list):
                    data[field] = [str(item).strip() for item in value if str(item).strip()]
                else:
                    data[field] = []

        # Add developers back to data
        data['developers'] = developer_ids
        if use_cases_value is not None:
            data['use_cases'] = use_cases_value

        print("7. Final data being sent to serializer:", data)
        print("=== DEBUG END ===")

        serializer = ServiceSerializer(instance, data=data, partial=True) if instance else ServiceSerializer(data=data)

        if not serializer.is_valid():
            print("Serializer errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        service = cast(Service, serializer.save())

        # Handle developers ManyToMany
        if 'developers' in data:
            print("8. Setting developers to service:", data['developers'])
            service.developers.set(data['developers'])

        print("9. Service developers after save:", list(service.developers.all()))

        return Response(
            ServiceSerializer(service).data,
            status=200 if instance else 201
        )

# ------------------ GIS SERVICE API ------------------
class GisServiceAPI(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAuthenticated()]

    def get(self, request, pk=None):
        queryset = GisService.objects.prefetch_related('developers')

        if pk:
            try:
                service = queryset.get(pk=pk)
            except GisService.DoesNotExist:
                try:
                    service = queryset.get(slug=pk)
                except GisService.DoesNotExist:
                    return Response({'error': 'Service not found'}, status=404)
            serializer = GisServiceSerializer(service)
            return Response(serializer.data)

        if request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            services = queryset.all()
            status_param = request.query_params.get('status')
            if status_param:
                services = services.filter(status=status_param)
        else:
            services = queryset
            status_param = request.query_params.get('status', 'active')
            if status_param:
                services = services.filter(status=status_param)
            exclude = request.query_params.get('exclude')
            if exclude:
                services = services.exclude(id=exclude)

        serializer = GisServiceSerializer(services, many=True)
        return Response(serializer.data)

    def post(self, request, pk=None):
        if pk is not None:
            return Response({"detail": "Method \"POST\" not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return self._save_service(request)

    def put(self, request, pk=None):
        try:
            service = GisService.objects.get(pk=pk)
        except GisService.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)
        return self._save_service(request, instance=service)

    def delete(self, request, pk=None):
        try:
            service = GisService.objects.get(pk=pk)
            service.delete()
            return Response(status=204)
        except GisService.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)

    def _save_service(self, request, instance=None):
        mutable_data = request.data.copy()

        developer_ids = []
        if hasattr(request.data, 'getlist') and request.data.getlist('developers'):
            dev_list = request.data.getlist('developers')
            for dev_item in dev_list:
                if isinstance(dev_item, str):
                    if dev_item.startswith('[') and dev_item.endswith(']'):
                        try:
                            parsed = json.loads(dev_item)
                            if isinstance(parsed, list):
                                for item in parsed:
                                    try:
                                        developer_ids.append(int(item))
                                    except (ValueError, TypeError):
                                        continue
                        except json.JSONDecodeError:
                            for id_str in dev_item.strip('[]').split(','):
                                try:
                                    developer_ids.append(int(id_str.strip()))
                                except ValueError:
                                    continue
                    else:
                        try:
                            developer_ids.append(int(dev_item))
                        except ValueError:
                            continue
                elif isinstance(dev_item, (int, float)):
                    developer_ids.append(int(dev_item))
        elif 'developers' in request.data:
            dev_value = request.data['developers']
            if isinstance(dev_value, str):
                if dev_value.strip() == '[]' or dev_value.strip() == '':
                    developer_ids = []
                else:
                    try:
                        parsed = json.loads(dev_value)
                        if isinstance(parsed, list):
                            for item in parsed:
                                try:
                                    developer_ids.append(int(item))
                                except (ValueError, TypeError):
                                    continue
                    except json.JSONDecodeError:
                        for id_str in dev_value.split(','):
                            try:
                                developer_ids.append(int(id_str.strip()))
                            except ValueError:
                                continue
            elif isinstance(dev_value, list):
                for item in dev_value:
                    try:
                        developer_ids.append(int(item))
                    except (ValueError, TypeError):
                        continue

        if 'developers' in mutable_data:
            del mutable_data['developers']

        list_fields = ['features', 'benefits', 'technologies']

        use_cases_value = None
        if 'use_cases' in mutable_data:
            raw_use_cases = mutable_data.get('use_cases')
            if isinstance(raw_use_cases, str):
                try:
                    parsed = json.loads(raw_use_cases)
                    use_cases_value = parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    use_cases_value = []
            elif isinstance(raw_use_cases, list):
                use_cases_value = raw_use_cases

        data = {}
        for key in mutable_data:
            if key in list_fields or key == 'use_cases':
                continue
            data[key] = mutable_data.get(key)

        for field in list_fields:
            if field in mutable_data:
                value = mutable_data[field]
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            data[field] = [str(item).strip() for item in parsed if str(item).strip()]
                        else:
                            items = []
                            for line in value.split('\n'):
                                items.extend([item.strip() for item in line.split(',') if item.strip()])
                            data[field] = items
                    except json.JSONDecodeError:
                        items = []
                        for line in value.split('\n'):
                            items.extend([item.strip() for item in line.split(',') if item.strip()])
                        data[field] = items
                elif isinstance(value, list):
                    data[field] = [str(item).strip() for item in value if str(item).strip()]
                else:
                    data[field] = []

        data['developers'] = developer_ids
        if use_cases_value is not None:
            data['use_cases'] = use_cases_value

        serializer = GisServiceSerializer(instance, data=data, partial=True) if instance else GisServiceSerializer(data=data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        service = cast(GisService, serializer.save())

        if 'developers' in data:
            service.developers.set(data['developers'])

        return Response(
            GisServiceSerializer(service).data,
            status=200 if instance else 201
        )


class GisServiceBySlugAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            service = GisService.objects.get(slug=slug)
        except GisService.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)

        if service.status != 'active':
            return Response({'error': 'Service not found'}, status=404)

        serializer = GisServiceSerializer(service)
        return Response(serializer.data)


class GisServiceExploreSubsectionAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request, service_slug, sub_slug):
        try:
            service = GisService.objects.get(slug=service_slug)
        except GisService.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)

        is_admin = bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )

        if not is_admin and service.status != 'active':
            return Response({'error': 'Service not found'}, status=404)

        explore = getattr(service, 'explore', None) or {}
        subsections = explore.get('subsections', []) if isinstance(explore, dict) else []

        if not isinstance(subsections, list):
            subsections = []

        match = None
        for subsection in subsections:
            if not isinstance(subsection, dict):
                continue
            if str(subsection.get('slug', '')).strip() == sub_slug:
                match = subsection
                break

        if not match:
            return Response({'error': 'Subsection not found'}, status=404)

        return Response(
            {
                'service_slug': service.slug,
                'service_title': service.title,
                'explore_title': (explore.get('title') if isinstance(explore, dict) else ''),
                'subsection': match,
            },
            status=status.HTTP_200_OK,
        )


class ServiceExploreSubsectionAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request, service_slug, sub_slug):
        try:
            service = Service.objects.get(slug=service_slug)
        except Service.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)

        is_admin = bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )

        if not is_admin and service.status != 'active':
            return Response({'error': 'Service not found'}, status=404)

        explore = getattr(service, 'explore', None) or {}
        subsections = explore.get('subsections', []) if isinstance(explore, dict) else []

        if not isinstance(subsections, list):
            subsections = []

        match = None
        for subsection in subsections:
            if not isinstance(subsection, dict):
                continue
            if str(subsection.get('slug', '')).strip() == sub_slug:
                match = subsection
                break

        if not match:
            return Response({'error': 'Subsection not found'}, status=404)

        return Response(
            {
                'service_slug': service.slug,
                'service_title': service.title,
                'explore_title': (explore.get('title') if isinstance(explore, dict) else ''),
                'subsection': match,
            },
            status=status.HTTP_200_OK,
        )


# ------------------ SERVICE SLUG API ------------------
class ServiceBySlugAPI(APIView):
    """Public endpoint to fetch a single service by its slug."""
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            service = Service.objects.get(slug=slug)
        except Service.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)

        if service.status != 'active':
            return Response({'error': 'Service not found'}, status=404)

        serializer = ServiceSerializer(service)
        return Response(serializer.data)


def _is_admin(user):
    return bool(user and getattr(user, "is_authenticated", False) and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) or getattr(user, "is_admin", False)))

def _can_manage_projects(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False) or getattr(user, "is_admin", False):
        return True
    usertype = getattr(user, "usertype", None)
    name = getattr(usertype, "name", None)
    if isinstance(name, str) and name.strip().lower() in {"founder", "director"}:
        return True
    employee_profile = getattr(user, "employee_profile", None)
    designation = getattr(employee_profile, "designation", None)
    if isinstance(designation, str) and "project manager" in designation.strip().lower():
        return True
    return False


def _preserve_private_plan_before_project_delete(project):
    private_plan = getattr(project, "private_project_plan", None)
    if private_plan is None:
        return

    preserved_project = Project.objects.create(
        title=(getattr(private_plan, "project_name", "") or "").strip() or f"Private Plan {project.pk}",
        description=getattr(private_plan, "project_description", "") or "",
        category=getattr(project, "category", "mobile") or "mobile",
        start_date=getattr(private_plan, "start_date", None),
        end_date=getattr(private_plan, "end_date", None),
        image=getattr(project, "image", None),
        image_url=getattr(project, "image_url", "") or "",
        shortDescription="",
        client=getattr(project, "client", "") or "",
        technologies=[],
        status="planned",
        timeline=getattr(private_plan, "timeline", "") or "",
        team="",
        project_manager=getattr(project, "project_manager", None),
        working_days=[],
        spare_until=None,
        rejoin_notes="",
        image_description="",
        work_goals="",
        goal_deadline=None,
        color=getattr(project, "color", "from-blue-500 to-purple-600") or "from-blue-500 to-purple-600",
        featured=False,
        details="",
        challenges=[],
        outcomes=[],
        stats={},
        gallery=[],
        icon=getattr(project, "icon", "Briefcase") or "Briefcase",
        liveUrl="",
        videoUrl="",
        sortOrder=getattr(project, "sortOrder", 0),
        testimonial_name="",
        testimonial_role="",
        testimonial_image="",
        testimonial_quote="",
        testimonial_rating=5,
    )
    private_plan.project = preserved_project
    private_plan.save(update_fields=["project"])
    EmployeeProfile.objects.filter(private_project_id=project.pk).update(
        private_project=preserved_project,
        updated_at=timezone.now(),
    )


class ProjectDraftAPI(DebugForce200Mixin, APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _payload(self, data=None):
        data = data or {}
        payload = {
            "id": "new",
            "title": "",
            "description": "",
            "status": "active",
            "goal": "",
            "deadline": None,
            "start_date": None,
            "end_date": None,
            "duration": "",
            "client": "",
            "budget": "",
            "project_manager": None,
            "image": None,
            "image_url": None,
            "technologies": [],
            "challenges": [],
            "outcomes": [],
            "stats": {},
            "gallery": [],
            "working_days": [],
            "team_members": [],
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
        }
        for key, value in data.items():
            payload[key] = value
        return payload

    def get(self, request):
        return Response(self._payload(), status=status.HTTP_200_OK)

    def patch(self, request):
        incoming = request.data if isinstance(request.data, dict) else {}
        return Response(self._payload(incoming), status=status.HTTP_200_OK)

    def post(self, request):
        return self.patch(request)

# ------------------ PROJECT API ------------------
class ProjectAPI(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAuthenticated()] 
    
    def get(self, request, pk=None):
        projects = Project.objects.filter(private_project_plan__isnull=True)
        if pk is not None:
            if request.query_params.get("include_plan") in ("1", "true", "yes"):
                project = (
                    Project.objects.select_related("project_manager", "current_project_plan", "private_project_plan")
                    .prefetch_related(
                        "current_project_plan__assignments",
                        "current_project_plan__assignments__daily_updates",
                        "current_project_plan__ticket_assignments",
                        "private_project_plan__assignments",
                        "private_project_plan__assignments__daily_updates",
                    )
                    .filter(pk=pk)
                    .first()
                )
                if project is None:
                    return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
                project_payload = ProjectSerializer(project, context={"request": request}).data
                plan = getattr(project, "current_project_plan", None) or getattr(project, "private_project_plan", None)
                if isinstance(plan, CurrentProjectPlan):
                    plan_payload = CurrentProjectPlanSerializer(plan, context={"request": request}).data
                else:
                    plan_payload = PrivateProjectPlanSerializer(plan, context={"request": request}).data if plan else None
                response_payload = dict(project_payload)
                response_payload["project"] = project_payload
                response_payload["plan"] = plan_payload
                return Response(response_payload, status=status.HTTP_200_OK)

            try:
                project = projects.get(pk=pk)
            except Project.DoesNotExist:
                return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
            serializer = ProjectSerializer(project, context={"request": request})
            payload = dict(serializer.data)
            payload.pop("employee_team_members", None)
            payload.pop("employee_team_members_data", None)
            return Response(payload, status=status.HTTP_200_OK)
        serializer = ProjectSerializer(projects, many=True, context={"request": request})
        data = list(serializer.data)
        for item in data:
            if isinstance(item, dict):
                item.pop("employee_team_members", None)
                item.pop("employee_team_members_data", None)
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request, pk=None):
        if pk is not None:
            return Response({"detail": "Method \"POST\" not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        if not _can_manage_projects(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return self.handle_project_request(request)
    
    def put(self, request, pk=None):
        if not _can_manage_projects(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        return self.handle_project_request(request, project, partial=False)

    def patch(self, request, pk=None):
        if not _can_manage_projects(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        return self.handle_project_request(request, project, partial=True)

    def delete(self, request, pk=None):
        if not _can_manage_projects(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        
        _preserve_private_plan_before_project_delete(project)
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def handle_project_request(self, request, instance=None, partial=False):
        data = {key: value for key, value in request.data.items()}
        
        json_fields = ['technologies', 'challenges', 'outcomes', 'stats', 'gallery', 'working_days', 'team_members']

        for field in json_fields:
            if field in data:
                field_value = data[field]

                if isinstance(field_value, str):
                    try:
                        data[field] = json.loads(field_value)
                    except json.JSONDecodeError:
                        if field in ['technologies', 'gallery']:
                            data[field] = [item.strip() for item in field_value.split(',') if item.strip()]
                        elif field in ['challenges', 'outcomes']:
                            data[field] = [item.strip() for item in field_value.split('\n') if item.strip()]
                        elif field == 'working_days':
                            data[field] = [item.strip() for item in field_value.split(',') if item.strip()]
                        elif field == 'team_members':
                            data[field] = [int(item.strip()) for item in field_value.split(',') if item.strip().isdigit()]
                        else:
                            data[field] = {}
                elif isinstance(field_value, list):
                    data[field] = [item.strip() if isinstance(item, str) else item for item in field_value if item]
                elif isinstance(field_value, dict):
                    data[field] = field_value
                else:
                    data[field] = {} if field == 'stats' else []

        for field in json_fields:
            if field not in data or data[field] is None:
                data[field] = [] if field in ['technologies', 'challenges', 'outcomes', 'gallery', 'working_days', 'team_members'] else {}

        # Handle uploaded gallery files
        gallery_files = request.FILES.getlist('gallery_files')
        for f in gallery_files:
            file_name = default_storage.save(f'projects/gallery/{f.name}', f)
            file_url = default_storage.url(file_name)
            data['gallery'].append(file_url)

        # Public `/api/projects/` must not accept or return internal employee assignment fields.
        data.pop("employee_team_members", None)

        if instance:
            serializer = ProjectSerializer(instance, data=data, partial=partial, context={"request": request})
        else:
            serializer = ProjectSerializer(data=data, context={"request": request})
            
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EmployeeProjectsAPI(DebugForce200Mixin, APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

    def get_permissions(self):
        if self.request.method == 'GET' and settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def _get_queryset(self, request):
        qs = Project.objects.all()
        if not getattr(request.user, "is_authenticated", False) and settings.DEBUG:
            return qs
        if _is_admin(request.user) or _can_manage_projects(request.user):
            return qs
        if not hasattr(request.user, "employee_profile"):
            return Project.objects.none()
        employee = request.user.employee_profile
        private_project_id = getattr(employee, "private_project_id", None)
        q = (
            Q(employee_team_members=employee)
            | Q(memberships__employee=employee, memberships__is_active=True)
            | Q(project_manager=request.user)
            | Q(current_project_plan__assignments__employee=employee)
            | Q(private_project_plan__assignments__employee=employee)
        )
        if private_project_id:
            q = q | Q(pk=private_project_id)
        return qs.filter(q).distinct()

    def get(self, request, pk=None):
        qs = self._get_queryset(request)
        if pk is not None:
            try:
                obj = qs.get(pk=pk)
            except Project.DoesNotExist:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(ProjectSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)
        serializer_cls = ProjectSerializer if request.query_params.get("full") in ("1", "true", "yes") else ProjectListSerializer
        if wants_pagination(request):
            paginator = DefaultPageNumberPagination()
            page = paginator.paginate_queryset(qs.order_by("-updated_at"), request)
            data = serializer_cls(page, many=True, context={"request": request}).data
            return paginator.get_paginated_response(data)
        return Response(serializer_cls(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request, pk=None):
        if pk is not None:
            return Response({"detail": "Method \"POST\" not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        if not _can_manage_projects(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return ProjectAPI().handle_project_request(request)

    def patch(self, request, pk=None):
        if not _can_manage_projects(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        return ProjectAPI().handle_project_request(request, project, partial=True)

    def put(self, request, pk=None):
        if not _can_manage_projects(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        return ProjectAPI().handle_project_request(request, project, partial=False)

    def delete(self, request, pk=None):
        if not _can_manage_projects(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        _preserve_private_plan_before_project_delete(project)
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectMembershipsAPI(APIView):
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    permission_classes = [IsAuthenticated]

    def _can_manage(self, user, project):
        if _is_admin(user) or _can_manage_projects(user):
            return True
        return bool(project and getattr(project, "project_manager_id", None) == getattr(user, "id", None))

    def get(self, request):
        project_id = request.query_params.get("project")
        if project_id in (None, "", "null"):
            return Response({"detail": "project is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            project = Project.objects.get(pk=int(str(project_id).strip()))
        except Exception:
            return Response({"detail": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        qs = ProjectMembership.objects.select_related("employee", "employee__user", "project").filter(project=project)
        if not self._can_manage(request.user, project):
            employee = getattr(request.user, "employee_profile", None)
            if not employee:
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            qs = qs.filter(employee=employee)

        return Response(ProjectMembershipSerializer(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request):
        project_id = request.data.get("project")
        if project_id in (None, "", "null"):
            return Response({"detail": "project is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            project = Project.objects.get(pk=int(str(project_id).strip()))
        except Exception:
            return Response({"detail": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        if not self._can_manage(request.user, project):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        rows = request.data.get("memberships")
        if not isinstance(rows, list):
            rows = [request.data]

        created_or_updated = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            employee_id = row.get("employee") or row.get("employee_id")
            role = row.get("role", "member")
            is_active = row.get("is_active", True)
            if employee_id in (None, "", "null"):
                continue
            try:
                employee = EmployeeProfile.objects.get(pk=int(str(employee_id).strip()))
            except Exception:
                continue
            membership, _ = ProjectMembership.objects.get_or_create(project=project, employee=employee)
            membership.role = role if isinstance(role, str) and role else membership.role
            membership.is_active = bool(is_active)
            membership.save()
            created_or_updated.append(membership)

        return Response(ProjectMembershipSerializer(created_or_updated, many=True, context={"request": request}).data, status=status.HTTP_200_OK)


class ProjectMembershipDetailAPI(APIView):
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    permission_classes = [IsAuthenticated]

    def _get(self, pk):
        try:
            return ProjectMembership.objects.select_related("employee", "employee__user", "project").get(pk=pk)
        except ProjectMembership.DoesNotExist:
            return None

    def _can_manage(self, user, project):
        if _is_admin(user) or _can_manage_projects(user):
            return True
        return bool(project and getattr(project, "project_manager_id", None) == getattr(user, "id", None))

    def patch(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not self._can_manage(request.user, obj.project):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ProjectMembershipSerializer(obj, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(ProjectMembershipSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not self._can_manage(request.user, obj.project):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------ GALLERY API ------------------
class GalleryAPI(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAuthenticated()]

    def get(self, request):
        images = GalleryItem.objects.all().order_by("-created_at")
        serializer = GalleryItemSerializer(images, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = GalleryItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GalleryDetailAPI(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAuthenticated()]

    def get(self, request, pk):
        try:
            item = GalleryItem.objects.get(id=pk)
            serializer = GalleryItemSerializer(item)
            return Response(serializer.data)
        except GalleryItem.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        try:
            item = GalleryItem.objects.get(id=pk)
        except GalleryItem.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = GalleryItemSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            item = GalleryItem.objects.get(id=pk)
        except GalleryItem.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------ PRODUCT API (COMPLETELY REWRITTEN) ------------------
class ProductAPI(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAuthenticated()]

    def get(self, request, pk=None):
        queryset = Product.objects.prefetch_related('gallery_images')

        if pk:
            try:
                product = queryset.get(pk=pk)
            except Product.DoesNotExist:
                return Response({'error': 'Product not found'}, status=404)
            return Response(ProductSerializer(product).data)

        return Response(ProductSerializer(queryset.all(), many=True).data)

    def post(self, request, pk=None):
        if pk is not None:
            return Response({"detail": "Method \"POST\" not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return self._save_product(request)

    def put(self, request, pk=None):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)
        return self._save_product(request, instance=product)

    def delete(self, request, pk=None):
        try:
            product = Product.objects.get(pk=pk)
            product.delete()
            return Response(status=204)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)

    def _save_product(self, request, instance=None):
        list_fields = [
            'features', 'outcomes', 'challenges',
            'technologies', 'stats',
            'platforms', 'integrations', 'support'
        ]

        incoming = request.data
        data = {}
        for key in incoming.keys():
            if key.startswith('gallery_'):
                continue
            if key in list_fields:
                continue
            data[key] = incoming.get(key)

        def _append_gallery_files(files):
            for f in files:
                if f:
                    gallery_files.append(f)

        gallery_files = []
        for key in request.FILES:
            if key.startswith('gallery_'):
                _append_gallery_files([request.FILES[key]])

        if hasattr(request.FILES, "getlist"):
            for key in ["gallery", "gallery[]", "images", "images[]"]:
                _append_gallery_files(request.FILES.getlist(key))

        def _strip_backticks(value):
            if not isinstance(value, str):
                return value
            text = value.strip()
            if len(text) >= 2 and text[0] == "`" and text[-1] == "`":
                return text[1:-1].strip()
            return text

        for url_field in ['liveUrl', 'demoUrl', 'documentationUrl']:
            if url_field in data:
                data[url_field] = _strip_backticks(data[url_field])

        def _coerce_scalar_to_str(value):
            if isinstance(value, (str, int, float, bool)):
                return str(value).strip()
            return None

        def _json_loads_if_possible(value):
            if not isinstance(value, str):
                return None
            text = value.strip()
            if text == "":
                return None
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return None

        for field in list_fields:
            if hasattr(incoming, "getlist"):
                raw_values = incoming.getlist(field)
            else:
                raw_values = incoming.get(field)

            if raw_values is None:
                continue

            raw_queue = raw_values if isinstance(raw_values, list) else [raw_values]

            if field == "stats":
                normalized_stats = []
                queue = list(raw_queue)
                while queue:
                    raw = queue.pop(0)
                    if raw in ["", None]:
                        continue
                    if isinstance(raw, dict):
                        normalized_stats.append(raw)
                        continue
                    if isinstance(raw, list):
                        queue = list(raw) + queue
                        continue
                    parsed = _json_loads_if_possible(raw)
                    if isinstance(parsed, dict):
                        normalized_stats.append(parsed)
                        continue
                    if isinstance(parsed, list):
                        queue = list(parsed) + queue
                        continue
                data[field] = normalized_stats
                continue

            normalized_strings = []
            queue = list(raw_queue)
            while queue:
                raw = queue.pop(0)
                if raw in ["", None]:
                    continue
                if isinstance(raw, list):
                    queue = list(raw) + queue
                    continue
                parsed = _json_loads_if_possible(raw)
                if isinstance(parsed, list):
                    queue = list(parsed) + queue
                    continue
                scalar = _coerce_scalar_to_str(parsed if parsed is not None else raw)
                if scalar:
                    normalized_strings.append(scalar)
            data[field] = normalized_strings

        serializer = (
            ProductSerializer(instance, data=data, partial=True)
            if instance else ProductSerializer(data=data)
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product = cast(Product, serializer.save())

        # 🔥 IMPORTANT: Handle gallery images
        if gallery_files:
            if instance:
                # Clear existing gallery if new files are uploaded
                product.gallery_images.all().delete()
            
            for img in gallery_files:
                ProductGallery.objects.create(product=product, image=img)

        # 🔹 Re-fetch with gallery
        product = Product.objects.prefetch_related('gallery_images').get(pk=product.pk)

        return Response(
            ProductSerializer(product).data,
            status=200 if instance else 201
        )


# ------------------ PRODUCT GALLERY API ------------------
class ProductGalleryAPI(APIView):
    parser_classes = [MultiPartParser, FormParser]
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAuthenticated()]

    def get(self, request, product_pk=None, gallery_pk=None):
        if not product_pk and not gallery_pk:
            gallery_images = ProductGallery.objects.all().order_by("-created_at")
            serializer = ProductGallerySerializer(gallery_images, many=True)
            return Response(serializer.data)
        
        elif product_pk and not gallery_pk:
            gallery_images = ProductGallery.objects.filter(product_id=product_pk).order_by("-created_at")
            serializer = ProductGallerySerializer(gallery_images, many=True)
            return Response(serializer.data)
        
        elif gallery_pk:
            try:
                gallery_item = ProductGallery.objects.get(pk=gallery_pk)
                serializer = ProductGallerySerializer(gallery_item)
                return Response(serializer.data)
            except ProductGallery.DoesNotExist:
                return Response({'error': 'Gallery image not found'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, product_pk=None):
        if not product_pk:
            return Response({'error': 'Product ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            product = Product.objects.get(pk=product_pk)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
        
        gallery_files = request.FILES.getlist('images')
        created_images = []
        
        for gallery_file in gallery_files:
            gallery_item = ProductGallery.objects.create(
                product=product,
                image=gallery_file
            )
            created_images.append(ProductGallerySerializer(gallery_item).data)
        
        return Response(created_images, status=status.HTTP_201_CREATED)

    def delete(self, request, gallery_pk=None, product_pk=None):
        if not gallery_pk:
            return Response({'error': 'Gallery image ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            gallery_item = ProductGallery.objects.get(pk=gallery_pk)
        except ProductGallery.DoesNotExist:
            return Response({'error': 'Gallery image not found'}, status=status.HTTP_404_NOT_FOUND)
        
        gallery_item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
