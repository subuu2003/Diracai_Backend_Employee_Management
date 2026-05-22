import json
from rest_framework import serializers
from django.utils.html import strip_tags
from django.core.files.uploadedfile import UploadedFile

from .models import (
    Testimonial,
    Service,
    GisService,
    TeamMember,
    Project,
    ProjectMembership,
    GalleryItem,
    Product,
    ProductGallery,
    Blog,
    BlogCategory,
    BlogComment,
)
from django.contrib.auth import get_user_model

User = get_user_model()
from account.employee_models import EmployeeProfile
from account.employee_serializers import PublicEmployeeSerializer

# ======================================================
# TEAM MEMBER (UNCHANGED)
# ======================================================

# ======================================================
# ✅ SERVICE SERIALIZER
# ======================================================

class TestimonialSerializer(serializers.ModelSerializer):
    """Serializer for Testimonial model"""
    
    class Meta:
        model = Testimonial
        fields = [
            'id',
            'name',
            'company',
            'role',
            'text',
            'image',
            'linkedin',
            'status',
            'sort_order',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_linkedin(self, value):
        """Validate LinkedIn URL or allow /#"""
        if value and value.strip():
            # Allow "/#" as a special value
            if value == "/#":
                return value
            
            # Also allow empty string
            if value == "":
                return "/#"  # Convert empty string to /# for consistency
            
            # Basic LinkedIn URL validation for actual LinkedIn URLs
            if not (value.startswith('https://linkedin.com/') or 
                    value.startswith('https://www.linkedin.com/')):
                raise serializers.ValidationError(
                    "Please provide a valid LinkedIn URL (starting with https://linkedin.com/) or use /# if not available"
                )
        else:
            # If value is None or empty, use /#
            return "/#"
        return value
    
    def to_representation(self, instance):
        """Ensure /# is returned for empty LinkedIn values"""
        representation = super().to_representation(instance)
        # If linkedin is None or empty in database, return /#
        if not representation.get('linkedin'):
            representation['linkedin'] = "/#"
        return representation

class ServiceSerializer(serializers.ModelSerializer):
    """
    Service Serializer following Product pattern
    """
    # read-only slug and id (id is primary key but our save logic will auto-populate it)
    slug = serializers.CharField(read_only=True)
    
    use_cases = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )
    # Explicit list fields to avoid JSON parsing issues
    features = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    
    benefits = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    
    technologies = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    explore = serializers.DictField(required=False, allow_null=True)
    
    # Developers as IDs (can be extended to nested serializers later)
    developers = serializers.PrimaryKeyRelatedField(
        queryset=TeamMember.objects.all(),
        many=True,
        required=False
    )
    
    class Meta:
        model = Service
        fields = [
            'id',
            'slug',
            'title',
            'description',
            # 'icon_name',
            'image',
            'long_description',
            'features',
            'benefits',
            'technologies',
            'developers',
            'demo_video_url',
            'status',
            'sort_order',
            'created_at',
            'updated_at',
            'use_cases',
            'explore',
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']

    def _clean_text(self, value):
        if value is None:
            return ""
        text = str(value).strip()
        while text.startswith(("`", '"', "'")) and text.endswith(("`", '"', "'")) and len(text) >= 2:
            text = text[1:-1].strip()
        return text

    def validate_image(self, value):
        if isinstance(value, str):
            cleaned = self._clean_text(value)
            return cleaned or None
        return value

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        if isinstance(rep.get("image"), str):
            rep["image"] = self._clean_text(rep["image"])

        use_cases = rep.get("use_cases")
        if isinstance(use_cases, list):
            cleaned_use_cases = []
            for item in use_cases:
                if not isinstance(item, dict):
                    continue
                cleaned_item = dict(item)
                if "image" in cleaned_item and isinstance(cleaned_item.get("image"), str):
                    cleaned_item["image"] = self._clean_text(cleaned_item["image"])
                cleaned_use_cases.append(cleaned_item)
            rep["use_cases"] = cleaned_use_cases

        explore = rep.get("explore")
        if isinstance(explore, dict):
            cleaned_explore = dict(explore)
            if isinstance(cleaned_explore.get("title"), str):
                cleaned_explore["title"] = self._clean_text(cleaned_explore.get("title"))

            subsections = cleaned_explore.get("subsections")
            if isinstance(subsections, list):
                cleaned_subsections = []
                for subsection in subsections:
                    if not isinstance(subsection, dict):
                        continue
                    cleaned_sub = dict(subsection)
                    images = cleaned_sub.get("images")
                    if isinstance(images, list):
                        cleaned_sub["images"] = [
                            self._clean_text(x) for x in images if self._clean_text(x)
                        ]
                    sub_use_cases = cleaned_sub.get("use_cases")
                    if isinstance(sub_use_cases, list):
                        cleaned_uc = []
                        for uc in sub_use_cases:
                            if not isinstance(uc, dict):
                                continue
                            cleaned_item = dict(uc)
                            if isinstance(cleaned_item.get("image"), str):
                                cleaned_item["image"] = self._clean_text(cleaned_item.get("image"))
                            cleaned_uc.append(cleaned_item)
                        cleaned_sub["use_cases"] = cleaned_uc
                    cleaned_subsections.append(cleaned_sub)
                cleaned_explore["subsections"] = cleaned_subsections

            rep["explore"] = cleaned_explore

        return rep

    def validate_use_cases(self, value):
        if not value:
            return []
        cleaned = []
        for item in value:
            if not isinstance(item, dict):
                continue
            title = self._clean_text(item.get("title", ""))
            description = self._clean_text(item.get("description", ""))
            image = self._clean_text(item.get("image", ""))
            layout = item.get("layout")
            if layout not in ["image_left", "image_right"]:
                layout = "image_left"
            if title or description or image:
                cleaned.append(
                    {
                        "title": title,
                        "description": description,
                        "image": image,
                        "layout": layout,
                    }
                )
        return cleaned
    
    def to_internal_value(self, data):
        """
        Handle FormData lists like your ProductSerializer
        """
        data = data.copy()

        if 'explore' in data and isinstance(data.get('explore'), str):
            try:
                parsed = json.loads(data.get('explore'))
                data['explore'] = parsed
            except json.JSONDecodeError:
                data['explore'] = {}
        
        # Handle JSON fields from FormData
        list_fields = ['features', 'benefits', 'technologies', 'developers']
        
        def normalize_string_list(value):
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    # Comma-separated or newline-separated strings
                    items = []
                    for line in value.split('\n'):
                        items.extend([item.strip() for item in line.split(',') if item.strip()])
                    return items
            return []
        
        if 'use_cases' in data:
            value = data['use_cases']
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        data['use_cases'] = parsed
                    else:
                        data['use_cases'] = []
                except json.JSONDecodeError:
                    data['use_cases'] = []
            elif isinstance(value, list):
                # Already a list – trust it
                pass
            else:
                data['use_cases'] = []
        
        for field in list_fields:
            if field in data:
                data[field] = normalize_string_list(data[field])
        
        return super().to_internal_value(data)

    def validate_explore(self, value):
        if value in (None, "", {}):
            return {}

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}

        if not isinstance(value, dict):
            raise serializers.ValidationError("explore must be an object")

        title = self._clean_text(value.get('title', ''))
        subsections = value.get('subsections', [])

        if subsections in (None, ""):
            subsections = []

        if not isinstance(subsections, list):
            raise serializers.ValidationError("explore.subsections must be an array")

        def normalize_str_list(raw):
            if raw in (None, ""):
                return []
            if isinstance(raw, list):
                return [self._clean_text(x) for x in raw if self._clean_text(x)]
            if isinstance(raw, str):
                text = raw.strip()
                if text == "":
                    return []
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [self._clean_text(x) for x in parsed if self._clean_text(x)]
                except json.JSONDecodeError:
                    pass
                parts = []
                for line in text.split('\n'):
                    parts.extend([p.strip() for p in line.split(',') if p.strip()])
                return [self._clean_text(x) for x in parts if self._clean_text(x)]
            return []

        def normalize_int_list(raw):
            if raw in (None, ""):
                return []
            if isinstance(raw, list):
                out = []
                for item in raw:
                    if isinstance(item, dict) and 'id' in item:
                        item = item.get('id')
                    try:
                        out.append(int(item))
                    except (ValueError, TypeError):
                        continue
                return out
            if isinstance(raw, str):
                text = raw.strip()
                if text == "" or text == "[]":
                    return []
                try:
                    parsed = json.loads(text)
                    return normalize_int_list(parsed)
                except json.JSONDecodeError:
                    out = []
                    for part in text.strip('[]').split(','):
                        try:
                            out.append(int(part.strip()))
                        except ValueError:
                            continue
                    return out
            return []

        cleaned_subsections = []
        for subsection in subsections:
            if subsection in (None, ""):
                continue

            if isinstance(subsection, str):
                try:
                    subsection = json.loads(subsection)
                except json.JSONDecodeError:
                    continue

            if not isinstance(subsection, dict):
                raise serializers.ValidationError("explore.subsections items must be objects")

            has_any = any(v not in (None, "", [], {}) for v in subsection.values())
            s_title = self._clean_text(subsection.get('title', ''))
            s_slug = self._clean_text(subsection.get('slug', ''))

            if has_any and not s_title:
                raise serializers.ValidationError("explore.subsections.title is required")
            if has_any and not s_slug:
                raise serializers.ValidationError("explore.subsections.slug is required")

            s_short = self._clean_text(subsection.get('short_description', ''))
            s_desc = self._clean_text(subsection.get('description', ''))

            s_images = normalize_str_list(subsection.get('images', []))
            s_tech = normalize_str_list(subsection.get('technologies', []))
            s_devs = normalize_int_list(subsection.get('developers', []))

            s_use_cases = subsection.get('use_cases', [])
            if isinstance(s_use_cases, str):
                try:
                    parsed_uc = json.loads(s_use_cases)
                    s_use_cases = parsed_uc if isinstance(parsed_uc, list) else []
                except json.JSONDecodeError:
                    s_use_cases = []
            if not isinstance(s_use_cases, list):
                s_use_cases = []
            s_use_cases = self.validate_use_cases(s_use_cases)

            cleaned_subsections.append(
                {
                    'title': s_title,
                    'slug': s_slug,
                    'short_description': s_short,
                    'description': s_desc,
                    'images': s_images,
                    'technologies': s_tech,
                    'developers': s_devs,
                    'use_cases': s_use_cases,
                }
            )

        return {
            'title': title,
            'subsections': cleaned_subsections,
        }


class GisServiceSerializer(ServiceSerializer):
    explore = serializers.DictField(required=False, allow_null=True)

    class Meta(ServiceSerializer.Meta):
        model = GisService
        fields = ServiceSerializer.Meta.fields

    def to_internal_value(self, data):
        data = data.copy()
        if 'explore' in data and isinstance(data.get('explore'), str):
            try:
                parsed = json.loads(data.get('explore'))
                data['explore'] = parsed
            except json.JSONDecodeError:
                data['explore'] = {}
        return super().to_internal_value(data)

    def validate_explore(self, value):
        if value in (None, "", {}):
            return {}

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}

        if not isinstance(value, dict):
            raise serializers.ValidationError("explore must be an object")

        title = self._clean_text(value.get('title', ''))
        subsections = value.get('subsections', [])

        if subsections in (None, ""):
            subsections = []

        if not isinstance(subsections, list):
            raise serializers.ValidationError("explore.subsections must be an array")

        def normalize_str_list(raw):
            if raw in (None, ""):
                return []
            if isinstance(raw, list):
                return [self._clean_text(x) for x in raw if self._clean_text(x)]
            if isinstance(raw, str):
                text = raw.strip()
                if text == "":
                    return []
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [self._clean_text(x) for x in parsed if self._clean_text(x)]
                except json.JSONDecodeError:
                    pass
                parts = []
                for line in text.split('\n'):
                    parts.extend([p.strip() for p in line.split(',') if p.strip()])
                return [self._clean_text(x) for x in parts if self._clean_text(x)]
            return []

        def normalize_int_list(raw):
            if raw in (None, ""):
                return []
            if isinstance(raw, list):
                out = []
                for item in raw:
                    if isinstance(item, dict) and 'id' in item:
                        item = item.get('id')
                    try:
                        out.append(int(item))
                    except (ValueError, TypeError):
                        continue
                return out
            if isinstance(raw, str):
                text = raw.strip()
                if text == "" or text == "[]":
                    return []
                try:
                    parsed = json.loads(text)
                    return normalize_int_list(parsed)
                except json.JSONDecodeError:
                    out = []
                    for part in text.strip('[]').split(','):
                        try:
                            out.append(int(part.strip()))
                        except ValueError:
                            continue
                    return out
            return []

        cleaned_subsections = []
        for subsection in subsections:
            if subsection in (None, ""):
                continue

            if isinstance(subsection, str):
                try:
                    subsection = json.loads(subsection)
                except json.JSONDecodeError:
                    continue

            if not isinstance(subsection, dict):
                raise serializers.ValidationError("explore.subsections items must be objects")

            has_any = any(v not in (None, "", [], {}) for v in subsection.values())
            s_title = self._clean_text(subsection.get('title', ''))
            s_slug = self._clean_text(subsection.get('slug', ''))

            if has_any and not s_title:
                raise serializers.ValidationError("explore.subsections.title is required")
            if has_any and not s_slug:
                raise serializers.ValidationError("explore.subsections.slug is required")

            s_short = self._clean_text(subsection.get('short_description', ''))
            s_desc = self._clean_text(subsection.get('description', ''))
            s_highlight = self._clean_text(subsection.get('highlight', ''))
            s_key_benefits = normalize_str_list(subsection.get('key_benefits', []))

            def normalize_card_block(raw_block):
                if not isinstance(raw_block, dict):
                    raw_block = {}
                return {
                    'title': self._clean_text(raw_block.get('title', '')),
                    'description': self._clean_text(raw_block.get('description', '')),
                    'features': normalize_str_list(raw_block.get('features', [])),
                }

            s_primary_block = normalize_card_block(subsection.get('primary_block', {}))
            s_secondary_block = normalize_card_block(subsection.get('secondary_block', {}))

            s_images = normalize_str_list(subsection.get('images', []))
            s_tech = normalize_str_list(subsection.get('technologies', []))
            s_devs = normalize_int_list(subsection.get('developers', []))

            s_use_cases = subsection.get('use_cases', [])
            if isinstance(s_use_cases, str):
                try:
                    parsed_uc = json.loads(s_use_cases)
                    s_use_cases = parsed_uc if isinstance(parsed_uc, list) else []
                except json.JSONDecodeError:
                    s_use_cases = []
            if not isinstance(s_use_cases, list):
                s_use_cases = []
            s_use_cases = self.validate_use_cases(s_use_cases)

            cleaned_subsections.append(
                {
                    'title': s_title,
                    'slug': s_slug,
                    'short_description': s_short,
                    'description': s_desc,
                    'highlight': s_highlight,
                    'key_benefits': s_key_benefits,
                    'primary_block': s_primary_block,
                    'secondary_block': s_secondary_block,
                    'images': s_images,
                    'technologies': s_tech,
                    'developers': s_devs,
                    'use_cases': s_use_cases,
                }
            )

        return {
            'title': title,
            'subsections': cleaned_subsections,
        }

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        explore = rep.get("explore")
        if isinstance(explore, dict):
            cleaned_explore = dict(explore)
            if isinstance(cleaned_explore.get("title"), str):
                cleaned_explore["title"] = self._clean_text(cleaned_explore.get("title"))

            subsections = cleaned_explore.get("subsections")
            if isinstance(subsections, list):
                cleaned_subsections = []
                for subsection in subsections:
                    if not isinstance(subsection, dict):
                        continue
                    cleaned_sub = dict(subsection)
                    images = cleaned_sub.get("images")
                    if isinstance(images, list):
                        cleaned_sub["images"] = [
                            self._clean_text(x) for x in images if self._clean_text(x)
                        ]
                    if isinstance(cleaned_sub.get("highlight"), str):
                        cleaned_sub["highlight"] = self._clean_text(cleaned_sub.get("highlight"))
                    key_benefits = cleaned_sub.get("key_benefits")
                    if isinstance(key_benefits, list):
                        cleaned_sub["key_benefits"] = [
                            self._clean_text(x) for x in key_benefits if self._clean_text(x)
                        ]
                    for block_key in ("primary_block", "secondary_block"):
                        block = cleaned_sub.get(block_key)
                        if isinstance(block, dict):
                            cleaned_block = dict(block)
                            if isinstance(cleaned_block.get("title"), str):
                                cleaned_block["title"] = self._clean_text(cleaned_block.get("title"))
                            if isinstance(cleaned_block.get("description"), str):
                                cleaned_block["description"] = self._clean_text(cleaned_block.get("description"))
                            features = cleaned_block.get("features")
                            if isinstance(features, list):
                                cleaned_block["features"] = [
                                    self._clean_text(x) for x in features if self._clean_text(x)
                                ]
                            cleaned_sub[block_key] = cleaned_block
                    use_cases = cleaned_sub.get("use_cases")
                    if isinstance(use_cases, list):
                        cleaned_uc = []
                        for uc in use_cases:
                            if not isinstance(uc, dict):
                                continue
                            cleaned_item = dict(uc)
                            if isinstance(cleaned_item.get("image"), str):
                                cleaned_item["image"] = self._clean_text(cleaned_item.get("image"))
                            cleaned_uc.append(cleaned_item)
                        cleaned_sub["use_cases"] = cleaned_uc

                    cleaned_subsections.append(cleaned_sub)
                cleaned_explore["subsections"] = cleaned_subsections

            rep["explore"] = cleaned_explore

        return rep


class TeamMemberSerializer(serializers.ModelSerializer):
    joinDate = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = TeamMember
        fields = "__all__"
        extra_kwargs = {
            "education": {"required": False, "allow_null": True},
            "joinDate": {"required": False, "allow_null": True},
            "skills": {"required": False},
            "image": {"required": False, "allow_null": True},
            "linkedin_url": {"required": False, "allow_null": True},
        }

    def validate_status(self, value):
        value = value.lower()
        if value == "active":
            return "Active"
        if value == "alumni":
            return "Alumni"
        raise serializers.ValidationError("Invalid status choice")


# ======================================================
# PROJECT (UNCHANGED)
# ======================================================
class ProjectSerializer(serializers.ModelSerializer):
    class _ImageFileOrUrlField(serializers.Field):
        def to_internal_value(self, data):
            if data is None:
                return None
            if isinstance(data, UploadedFile):
                return data
            if isinstance(data, str):
                cleaned = data.strip().strip("`").strip()
                return cleaned
            raise serializers.ValidationError("Invalid image value")

        def to_representation(self, value):
            if not value:
                return None
            request = self.context.get("request")
            try:
                url = value.url
            except Exception:
                return None
            if request:
                try:
                    return request.build_absolute_uri(url)
                except Exception:
                    return url
            return url

    image = _ImageFileOrUrlField(required=False, allow_null=True)
    team_members = serializers.PrimaryKeyRelatedField(queryset=TeamMember.objects.all(), many=True, required=False)
    team_members_data = TeamMemberSerializer(source='team_members', many=True, read_only=True)
    employee_team_members = serializers.PrimaryKeyRelatedField(queryset=EmployeeProfile.objects.all(), many=True, required=False)
    employee_team_members_data = PublicEmployeeSerializer(source='employee_team_members', many=True, read_only=True)
    project_manager = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    project_manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = "__all__"

    def get_project_manager_name(self, obj):
        user = getattr(obj, 'project_manager', None)
        if not user:
            return None
        first = getattr(user, 'firstname', '') or ''
        last = getattr(user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(user, 'username', None)


class ProjectListSerializer(serializers.ModelSerializer):
    image = ProjectSerializer._ImageFileOrUrlField(required=False, allow_null=True)
    project_manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "description",
            "shortDescription",
            "status",
            "timeline",
            "start_date",
            "end_date",
            "image",
            "image_url",
            "project_manager",
            "project_manager_name",
            "updated_at",
            "created_at",
            "color",
        ]

    def get_project_manager_name(self, obj):
        user = getattr(obj, 'project_manager', None)
        if not user:
            return None
        first = getattr(user, 'firstname', '') or ''
        last = getattr(user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(user, 'username', None)


class ProjectMembershipSerializer(serializers.ModelSerializer):
    employee = serializers.SerializerMethodField()

    class Meta:
        model = ProjectMembership
        fields = [
            'id',
            'project',
            'employee',
            'role',
            'is_active',
            'joined_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'joined_at', 'updated_at']

    def get_employee(self, obj):
        e = getattr(obj, 'employee', None)
        if not e:
            return None
        user = getattr(e, 'user', None)
        first = getattr(user, 'firstname', '') or ''
        last = getattr(user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        name = full or getattr(user, 'username', '') or getattr(user, 'email', '') or ''
        return {
            "id": e.id,
            "employee_code": getattr(e, "employee_id", ""),
            "name": name,
            "email": getattr(user, "email", "") or "",
        }

    def update(self, instance, validated_data):
        image_value = validated_data.pop("image", serializers.empty)
        if image_value is not serializers.empty:
            if isinstance(image_value, UploadedFile):
                instance.image = image_value
                instance.image_url = ""
            elif isinstance(image_value, str):
                instance.image_url = image_value
        return super().update(instance, validated_data)

    def create(self, validated_data):
        image_value = validated_data.pop("image", serializers.empty)
        if image_value is not serializers.empty:
            if isinstance(image_value, UploadedFile):
                validated_data["image"] = image_value
            elif isinstance(image_value, str):
                validated_data["image_url"] = image_value
        return super().create(validated_data)

# ======================================================
# SITE GALLERY (UNCHANGED)
# ======================================================
class GalleryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = GalleryItem
        fields = "__all__"


# ======================================================
# ✅ PRODUCT GALLERY (FINAL – SAFE)
# ======================================================
class ProductGallerySerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = ProductGallery
        fields = ["id", "image", "created_at"]
        read_only_fields = fields


# ======================================================
# ✅ PRODUCT SERIALIZER (FINAL FIX)
# ======================================================
class ProductSerializer(serializers.ModelSerializer):
    """
    🔒 EXPLICIT LIST FIELDS
    This avoids DRF JSONField auto-parsing issues with FormData
    """

    features = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    outcomes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    challenges = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    technologies = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    stats = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )

    platforms = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    integrations = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    support = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    # 🔗 Gallery (read-only, created in view)
    gallery_images = ProductGallerySerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "tagline",
            "iconText",
            "cover",
            "description",
            "fullDescription",
            "category",
            "status",
            "features",
            "outcomes",
            "challenges",
            "technologies",
            "stats",
            "platforms",
            "integrations",
            "support",
            "liveUrl",
            "demoUrl",
            "documentationUrl",
            "pricing",
            "featured",
            "sortOrder",
            "gallery_images",
            "created_at",
            "updated_at",
        ]


    # --------------------------------------------------
    # 🔥 CRITICAL NORMALIZER (THE REAL FIX)
    # --------------------------------------------------
    def to_internal_value(self, data):
        """
        Accepts:
        - JSON strings: '["React"]'
        - FormData lists: ["React"]
        - Empty strings / junk safely
        """
        data = data.copy()

        list_fields = [
            "features",
            "outcomes",
            "challenges",
            "technologies",
            "stats",
            "platforms",
            "integrations",
            "support",
        ]

        def flatten(items):
            flattened = []
            for item in items:
                if isinstance(item, list):
                    flattened.extend(flatten(item))
                else:
                    flattened.append(item)
            return flattened

        def normalize_string_list(value):
            if isinstance(value, list):
                value = flatten(value)
                cleaned = []
                for item in value:
                    if item in ["", None]:
                        continue
                    if isinstance(item, str):
                        text = item.strip()
                        if text == "":
                            continue
                        try:
                            parsed = json.loads(text)
                        except json.JSONDecodeError:
                            cleaned.append(text)
                            continue
                        if isinstance(parsed, list):
                            cleaned.extend(normalize_string_list(parsed))
                            continue
                        if isinstance(parsed, (str, int, float, bool)):
                            cleaned.append(str(parsed))
                            continue
                        continue
                    if isinstance(item, (int, float, bool)):
                        cleaned.append(str(item))
                        continue
                return cleaned
            if isinstance(value, str):
                text = value.strip()
                if text == "":
                    return []
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    return []
                if isinstance(parsed, list):
                    return normalize_string_list(parsed)
                return []
            return []

        def normalize_stats_list(value):
            if isinstance(value, list):
                value = flatten(value)
                cleaned = []
                for item in value:
                    if item in ["", None]:
                        continue
                    if isinstance(item, str):
                        text = item.strip()
                        if text == "":
                            continue
                        try:
                            parsed = json.loads(text)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(parsed, dict):
                            cleaned.append(parsed)
                            continue
                        if isinstance(parsed, list):
                            cleaned.extend(normalize_stats_list(parsed))
                            continue
                        continue
                    if isinstance(item, dict):
                        cleaned.append(item)
                        continue
                return cleaned
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return normalize_stats_list(parsed)
                except json.JSONDecodeError:
                    return []
            return []

        url_fields = ["liveUrl", "demoUrl", "documentationUrl"]
        for field in url_fields:
            if field not in data:
                continue
            value = data[field]
            if not isinstance(value, str):
                continue
            text = value.strip()
            if len(text) >= 2 and text[0] == "`" and text[-1] == "`":
                text = text[1:-1].strip()
            data[field] = text

        for field in list_fields:
            if field not in data:
                continue

            value = data[field]

            if field == "stats":
                data[field] = normalize_stats_list(value)
                continue

            data[field] = normalize_string_list(value)

        return super().to_internal_value(data)


    # --------------------------------------------------
    # Stats validation (kept strict)
    # --------------------------------------------------
    def validate_stats(self, value):
        for stat in value:
            if not isinstance(stat, dict):
                raise serializers.ValidationError("Each stat must be an object")
            if "label" not in stat or "value" not in stat:
                raise serializers.ValidationError(
                    "Each stat must have 'label' and 'value'"
                )
        return value


    # Prevent nested writes (gallery handled separately)
    def create(self, validated_data):
        validated_data.pop("gallery_images", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("gallery_images", None)
        return super().update(instance, validated_data)

     # ============================
# Blog Serializers (NEW)
# ============================



class PublicBlogSerializer(serializers.ModelSerializer):
    """
    Serializer used by frontend (/blog page).
    Safe, explicit, and frontend-compatible.
    """

    tags = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    readingTime = serializers.SerializerMethodField()
    featured = serializers.BooleanField()
    content = serializers.SerializerMethodField()

    class Meta:
        model = Blog
        fields = [
            "id",
            "slug",
            "title",
            "excerpt",
            "content",
            "category",
            "tags",
            "image",
            "author",
            "date",
            "readingTime",
            "featured",
        ]
    def get_content(self, obj):
        """Return content with preserved formatting"""
        content = obj.content or ""
        # You can add markdown processing here if needed
        return content
    
    def get_tags(self, obj):
        # Supports CharField or JSONField
        if not obj.tags:
            return []
        if isinstance(obj.tags, list):
            return obj.tags
        return [t.strip() for t in obj.tags.split(",") if t.strip()]

    def get_author(self, obj):
        avatar_url = ""
        if getattr(obj, "author_avatar", None):
            try:
                avatar_url = obj.author_avatar.url
            except Exception:
                avatar_url = ""
        if not avatar_url:
            avatar_url = getattr(obj, "author_avatar_url", "") or ""
        return {
            "name": obj.author_name or "",
            "role": obj.author_role or "",
            "avatar": avatar_url,
        }

    def get_image(self, obj):
        if getattr(obj, "banner_image", None):
            try:
                return obj.banner_image.url
            except Exception:
                pass
        return getattr(obj, "banner_image_url", "") or ""

    def get_date(self, obj):
        # Frontend expects readable string
        return obj.published_at.strftime("%b %d, %Y") if obj.published_at else ""

    def get_readingTime(self, obj):
        # Approx: 200 words per minute
        if not obj.content:
            return 1
        words = len(obj.content.split())
        return max(1, round(words / 200))
# ✅ ADMIN BLOG SERIALIZER (Writable)
class BlogAdminSerializer(serializers.ModelSerializer):
    tags = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            normalized = {}
            for key in data.keys():
                values = data.getlist(key)
                if len(values) == 1:
                    normalized[key] = values[0]
                else:
                    normalized[key] = values
            data = normalized
        else:
            data = data.copy()

        if "tags" in data:
            value = data["tags"]
            if isinstance(value, str):
                text = value.strip()
                if text:
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, list):
                            data["tags"] = [str(x).strip() for x in parsed if str(x).strip()]
                        else:
                            data["tags"] = [t.strip() for t in text.split(",") if t.strip()]
                    except json.JSONDecodeError:
                        data["tags"] = [t.strip() for t in text.split(",") if t.strip()]
                else:
                    data["tags"] = []
            elif isinstance(value, list):
                cleaned = []
                for item in value:
                    if item in ["", None]:
                        continue
                    if isinstance(item, str):
                        s = item.strip()
                        if not s:
                            continue
                        try:
                            parsed = json.loads(s)
                            if isinstance(parsed, list):
                                cleaned.extend([str(x).strip() for x in parsed if str(x).strip()])
                                continue
                        except json.JSONDecodeError:
                            pass
                        cleaned.append(s)
                    else:
                        cleaned.append(str(item).strip())
                data["tags"] = [t for t in cleaned if t]
            else:
                data["tags"] = []

        return super().to_internal_value(data)

    class Meta:
        model = Blog
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "content",
            "category",
            "tags",
            "banner_image",
            "banner_image_url",
            "author_name",
            "author_avatar",
            "author_avatar_url",
            "author_role",
            "status",
            "featured",
            "meta_title",
            "meta_description",
            "canonical_url",
            "allow_indexing",
            "created_at",
            "updated_at",
            "published_at",
        ]
        read_only_fields = ["created_at", "updated_at", "published_at"]


class BlogCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogCategory
        fields = ["id", "name", "slug"]


class BlogCommentSerializer(serializers.ModelSerializer):
    blog = serializers.SlugRelatedField(read_only=True, slug_field="slug")

    class Meta:
        model = BlogComment
        fields = ["id", "blog", "name", "content", "created_at"]
        read_only_fields = fields


class BlogCommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogComment
        fields = ["name", "email", "content"]

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name is required")
        if len(value) > 120:
            raise serializers.ValidationError("Name is too long")
        return value

    def validate_content(self, value):
        value = value or ""
        cleaned = strip_tags(value).strip()
        if not cleaned:
            raise serializers.ValidationError("Content is required")
        if len(cleaned) > 5000:
            raise serializers.ValidationError("Content is too long")
        return cleaned


class BlogCommentAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogComment
        fields = [
            "id",
            "blog",
            "user",
            "name",
            "email",
            "content",
            "status",
            "ip_address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
