from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from account.employee_models import EmployeeProfile, OTPVerification
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.files.uploadedfile import UploadedFile
from django.apps import apps
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.db import IntegrityError

User = get_user_model()

def _clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    while text.startswith(("`", '"', "'")) and text.endswith(("`", '"', "'")) and len(text) >= 2:
        text = text[1:-1].strip()
    return text

def _resolve_employee_current_project(employee):
    project_id = getattr(employee, "private_project_id", None) or getattr(employee, "current_project_id", None)
    if project_id:
        return getattr(employee, "private_project", None) or getattr(employee, "current_project", None)
    try:
        Project = apps.get_model("account", "Project")
    except Exception:
        return None
    try:
        project = Project.objects.filter(memberships__employee=employee, memberships__is_active=True).order_by("-updated_at").first()
        if project:
            return project
        project = Project.objects.filter(employee_team_members=employee).order_by("-updated_at").first()
        if project:
            return project
        user = getattr(employee, "user", None)
        if user:
            project = Project.objects.filter(project_manager=user).order_by("-updated_at").first()
            if project:
                return project
    except Exception:
        return None
    return None


def _employee_document_api_url(request, employee_id, document_id):
    path = f"/api/employees/{employee_id}/documents/{document_id}/"
    if request:
        try:
            return request.build_absolute_uri(path)
        except Exception:
            return path
    return path


def _employee_integrity_error_detail(exc):
    message = _clean_text(exc)
    lowered = message.lower()
    duplicate_tokens = ("duplicate key value", "unique constraint", "unique failed")
    login_tokens = ("email", "username")

    if any(token in lowered for token in duplicate_tokens) and any(token in lowered for token in login_tokens):
        return {"email": "Email/login already exists."}

    return {"detail": message or "Employee creation failed due to a database constraint."}


class EmployeeProfileSerializer(serializers.ModelSerializer):
    """Serializer for Employee Profile"""
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    designation = serializers.CharField(required=False, allow_blank=True)
    profile_pic = serializers.SerializerMethodField()
    private_project = serializers.SerializerMethodField()
    private_project_title = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeProfile
        fields = [
            'id', 'user_id', 'username', 'employee_id', 'phone', 'designation', 'qualification', 'employment_type', 'location',
            'profile_pic',
            'status', 'is_active', 'has_password', 'private_project', 'private_project_title', 'documents',
            'user_email', 'user_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_user_name(self, obj):
        first = getattr(obj.user, 'firstname', '') or ''
        last = getattr(obj.user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(obj.user, 'username', '')

    def get_profile_pic(self, obj):
        img = getattr(obj.user, 'profile_image', None)
        try:
            url = _clean_text(img.url) if img else None
        except Exception:
            url = None
        if not url:
            return None
        request = self.context.get("request")
        if request and isinstance(url, str) and not url.lower().startswith(("http://", "https://")):
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

    def get_private_project(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "id", None) if project else None

    def get_private_project_title(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "title", None) if project else None

    def get_is_active(self, obj):
        return obj.status == 'active'

    def get_has_password(self, obj):
        try:
            return obj.user.has_usable_password()
        except Exception:
            return False

    def get_documents(self, obj):
        return [
            {
                "id": d.id,
                "title": d.title,
                "description": d.description,
                "document_type": d.document_type,
                "document_url": _employee_document_api_url(self.context.get("request"), obj.id, d.id),
                "status": d.status,
                "uploaded_at": d.uploaded_at,
                "updated_at": d.updated_at,
            }
            for d in obj.documents.all().order_by("-uploaded_at")
        ]


class EmployeeLoginSerializer(serializers.Serializer):
    """
    Serializer for employee login.

    Accepts:
    - Email
    - Phone
    - Username
    - Employee ID
    """
    login_id = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        login_id = (attrs.get('login_id') or '').strip()
        password = attrs.get('password')

        if not login_id:
            raise serializers.ValidationError(
                'Email, phone, username, or employee ID is required.',
                code='authorization'
            )

        user = None

        # 1. Try email
        user = User.objects.filter(
            email__iexact=login_id
        ).first()

        # 2. Try username
        if user is None:
            user = User.objects.filter(
                username__iexact=login_id
            ).first()

        # 3. Try phone from EmployeeProfile
        if user is None:
            employee = EmployeeProfile.objects.filter(
                phone__iexact=login_id
            ).select_related('user').first()

            if employee:
                user = employee.user

        # 4. Try employee ID
        if user is None:
            employee = EmployeeProfile.objects.filter(
                employee_id__iexact=login_id
            ).select_related('user').first()

            if employee:
                user = employee.user

        # No matching user
        if user is None:
            raise serializers.ValidationError(
                'Unable to log in with provided credentials.',
                code='authorization'
            )

        # Verify password
        if not user.check_password(password):
            raise serializers.ValidationError(
                'Unable to log in with provided credentials.',
                code='authorization'
            )

        # Check employee profile
        employee_profile = getattr(user, 'employee_profile', None)

        if employee_profile is None:
            raise serializers.ValidationError(
                'This user is not an employee.',
                code='authorization'
            )

        # Check active status
        if employee_profile.status != 'active':
            raise serializers.ValidationError(
                'This employee account is inactive. Please contact admin.',
                code='inactive'
            )

        attrs['user'] = user
        attrs['employee'] = employee_profile

        return attrs


class OTPSendSerializer(serializers.Serializer):
    """
    Serializer to request OTP for employee.

    Accepts:
    - Email
    - Phone
    - Username
    - Employee ID
    """
    login_id = serializers.CharField()
    password = serializers.CharField(write_only=True)

    class Meta:
        fields = ['login_id', 'password']

    def validate(self, attrs):
        login_id = (attrs.get('login_id') or '').strip()
        password = attrs.get('password')

        if not login_id:
            raise serializers.ValidationError(
                'Email, phone, username, or employee ID is required.',
                code='not_found'
            )

        user = None

        # 1. Email
        user = User.objects.filter(
            email__iexact=login_id
        ).first()

        # 2. Username
        if user is None:
            user = User.objects.filter(
                username__iexact=login_id
            ).first()

        # 3. Phone
        if user is None:
            employee = EmployeeProfile.objects.filter(
                phone__iexact=login_id
            ).select_related('user').first()

            if employee:
                user = employee.user

        # 4. Employee ID
        if user is None:
            employee = EmployeeProfile.objects.filter(
                employee_id__iexact=login_id
            ).select_related('user').first()

            if employee:
                user = employee.user

        # No user found
        if user is None:
            raise serializers.ValidationError(
                'Unable to find user with provided credentials.',
                code='not_found'
            )

        # Verify password
        if not user.check_password(password):
            raise serializers.ValidationError(
                'Invalid password.',
                code='invalid_password'
            )

        # Employee profile
        employee_profile = getattr(user, 'employee_profile', None)

        if employee_profile is None:
            raise serializers.ValidationError(
                'This user is not an employee.',
                code='not_employee'
            )

        # Active status
        if employee_profile.status != 'active':
            raise serializers.ValidationError(
                'This employee account is inactive.',
                code='inactive'
            )

        attrs['user'] = user
        attrs['employee'] = employee_profile

        return attrs

class OTPVerifySerializer(serializers.Serializer):
    """
    Serializer to verify OTP and return tokens
    """
    employee_id = serializers.CharField()
    otp_code = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        """Validate OTP"""
        employee_id = attrs.get('employee_id')
        otp_code = attrs.get('otp_code')

        try:
            employee = EmployeeProfile.objects.get(employee_id=employee_id)
        except EmployeeProfile.DoesNotExist:
            msg = 'Employee not found.'
            raise serializers.ValidationError(msg, code='not_found')

        if employee.status != 'active':
            msg = 'Pending admin approval.'
            raise serializers.ValidationError(msg, code='inactive')

        # Get the latest OTP verification for this employee
        try:
            otp_record = OTPVerification.objects.filter(
                employee=employee,
                is_verified=False
            ).latest('created_at')
        except OTPVerification.DoesNotExist:
            msg = 'No OTP found. Please request a new one.'
            raise serializers.ValidationError(msg, code='otp_not_found')

        # Check if OTP is expired
        if otp_record.is_expired():
            msg = 'OTP has expired. Please request a new one.'
            raise serializers.ValidationError(msg, code='otp_expired')

        # Check if OTP is correct
        if otp_record.otp_code != otp_code:
            otp_record.attempts += 1
            otp_record.save()
            
            remaining_attempts = otp_record.max_attempts - otp_record.attempts
            msg = f'Invalid OTP. {remaining_attempts} attempts remaining.'
            raise serializers.ValidationError(msg, code='invalid_otp')

        # Check if max attempts reached
        if otp_record.attempts >= otp_record.max_attempts:
            msg = 'Maximum OTP attempts exceeded.'
            raise serializers.ValidationError(msg, code='max_attempts_exceeded')

        attrs['employee'] = employee
        attrs['otp_record'] = otp_record
        return attrs


class EmployeeRegisterSerializer(serializers.Serializer):
    """
    Serializer for new employee registration
    """
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)
    location = serializers.CharField(max_length=200, required=False)
    designation = serializers.CharField(max_length=100, required=False)


    def validate_email(self, value):
        """Check if email already exists"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('Email already registered.')
        return value

    def validate_phone(self, value):
        """Check if phone already exists"""
        if EmployeeProfile.objects.filter(phone=value).exists():
            raise serializers.ValidationError('Phone number already registered.')
        return value

    def create(self, validated_data):
        """Create new employee user and profile"""
        # Split name into first and last name
        name_parts = validated_data['name'].split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        # Create user
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            phoneno=validated_data['phone'],
            password=validated_data['password'],
        )
        user.firstname = first_name
        user.lastname = last_name
        user.save()

        # Generate employee ID
        employee_count = EmployeeProfile.objects.count() + 1
        employee_id = f'DI{10000 + employee_count}'

        # Create employee profile
        employee_profile = EmployeeProfile.objects.create(
            user=user,
            employee_id=employee_id,
            phone=validated_data['phone'],
            designation=validated_data.get('designation', 'Applicant'),
            location=validated_data.get('location', ''),
            status='inactive',  # New employees start as inactive, require admin approval
        )

        return employee_profile


class EmployeeTokenSerializer(serializers.Serializer):
    """
    Serializer to return JWT tokens for authenticated employee
    """
    access = serializers.SerializerMethodField()
    refresh = serializers.SerializerMethodField()
    employee = EmployeeProfileSerializer(read_only=True)

    def get_access(self, obj):
        """Get access token from user"""
        user = obj.get('user')
        if user:
            refresh = RefreshToken.for_user(user)
            return str(refresh.access_token)
        return None

    def get_refresh(self, obj):
        """Get refresh token from user"""
        user = obj.get('user')
        if user:
            refresh = RefreshToken.for_user(user)
            return str(refresh)
        return None

    def to_representation(self, instance):
        """Use employee_profile instead of user in response"""
        ret = super().to_representation(instance)
        if 'user' in instance:
            ret['employee'] = EmployeeProfileSerializer(
                instance['user'].employee_profile
            ).data
        return ret


class PublicEmployeeSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    profile_pic = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    phone = serializers.CharField(read_only=True)
    private_project = serializers.SerializerMethodField()
    private_project_title = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeProfile
        fields = [
            'id',
            'employee_id',
            'name',
            'phone',
            'designation',
            'qualification',
            'employment_type',
            'profile_pic',
            'location',
            'status',
            'is_active',
            'private_project',
            'private_project_title',
            'documents',
            'linkedin_url',
            'created_at',
            'updated_at',
        ]

    def get_name(self, obj):
        first = getattr(obj.user, 'firstname', '') or ''
        last = getattr(obj.user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(obj.user, 'username', '')

    def get_profile_pic(self, obj):
        img = getattr(obj.user, 'profile_image', None)
        try:
            url = _clean_text(img.url) if img else None
        except Exception:
            url = None
        if not url:
            return None
        request = self.context.get("request")
        if request and isinstance(url, str) and not url.lower().startswith(("http://", "https://")):
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

    def get_is_active(self, obj):
        return obj.status == 'active'

    def get_private_project(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "id", None) if project else None

    def get_private_project_title(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "title", None) if project else None

    def get_documents(self, obj):
        docs = []
        for d in obj.documents.all().order_by("-uploaded_at"):
            docs.append(
                {
                    "id": d.id,
                    "title": d.title,
                    "description": d.description,
                    "document_type": d.document_type,
                    "document_url": _employee_document_api_url(self.context.get("request"), obj.id, d.id),
                    "status": d.status,
                    "uploaded_at": d.uploaded_at,
                    "updated_at": d.updated_at,
                }
            )
        return docs


class PublicEmployeeListSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    profile_pic = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    private_project = serializers.SerializerMethodField()
    private_project_title = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeProfile
        fields = [
            'id',
            'employee_id',
            'name',
            'designation',
            'profile_pic',
            'status',
            'is_active',
            'private_project',
            'private_project_title',
            'linkedin_url',
            'created_at',
            'updated_at',
        ]

    def get_name(self, obj):
        first = getattr(obj.user, 'firstname', '') or ''
        last = getattr(obj.user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(obj.user, 'username', '')

    def get_profile_pic(self, obj):
        img = getattr(obj.user, 'profile_image', None)
        try:
            url = _clean_text(img.url) if img else None
        except Exception:
            url = None
        if not url:
            return None
        request = self.context.get("request")
        if request and isinstance(url, str) and not url.lower().startswith(("http://", "https://")):
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

    def get_is_active(self, obj):
        return obj.status == 'active'

    def get_private_project(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "id", None) if project else None

    def get_private_project_title(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "title", None) if project else None


class EmployeeAdminSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', required=False)
    login_id = serializers.SerializerMethodField()
    status = serializers.CharField(required=False)
    employee_id = serializers.CharField(required=False, allow_blank=True)
    designation = serializers.CharField(required=False, allow_blank=True)
    private_project = serializers.PrimaryKeyRelatedField(
        queryset=apps.get_model("account", "Project").objects.all(),
        required=False,
        allow_null=True,
    )
    private_project_title = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    profile_pic = serializers.SerializerMethodField()
    profile_image = serializers.FileField(source='user.profile_image', required=False, allow_null=True, write_only=True)
    has_password = serializers.SerializerMethodField()
    employment_type = serializers.CharField(required=False, allow_blank=True)
    qualification = serializers.CharField(required=False, allow_blank=True)
    documents = serializers.SerializerMethodField()
    joining_documents = serializers.SerializerMethodField()
    documents_submitted_to_admin = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeProfile
        fields = [
            'id',
            'employee_id',
            'login_id',
            'name',
            'email',
            'phone',
            'designation',
            'profile_pic',
            'profile_image',
            'location',
            'employment_type',
            'qualification',
            'documents',
            'joining_documents',
            'documents_submitted_to_admin',
            'status',
            'is_active',
            'has_password',
            'private_project',
            'private_project_title',
            'linkedin_url',
            'created_at',
            'updated_at',
        ]

    def to_internal_value(self, data):
        data = data.copy()
        if "private_project" not in data:
            if "private_project_id" in data:
                data["private_project"] = data.get("private_project_id")
            elif "current_project" in data:
                data["private_project"] = data.get("current_project")
            elif "current_project_id" in data:
                data["private_project"] = data.get("current_project_id")
        if 'is_active' in data and 'status' not in data:
            data['status'] = data.get('is_active')
            data.pop('is_active', None)
        if 'status' in data:
            raw = data.get('status')
            if isinstance(raw, bool):
                data['status'] = 'active' if raw else 'inactive'
            elif isinstance(raw, int) and raw in (0, 1):
                data['status'] = 'active' if raw == 1 else 'inactive'
        return super().to_internal_value(data)

    def validate_status(self, value):
        if isinstance(value, bool):
            return 'active' if value else 'inactive'
        if isinstance(value, int) and value in (0, 1):
            return 'active' if value == 1 else 'inactive'
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ('true', '1', 'active'):
                return 'active'
            if v in ('false', '0', 'inactive', 'pending'):
                return 'inactive'
        return value

    def get_name(self, obj):
        first = getattr(obj.user, 'firstname', '') or ''
        last = getattr(obj.user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(obj.user, 'username', '')

    def get_is_active(self, obj):
        return obj.status == 'active'

    def get_login_id(self, obj):
        email = getattr(obj.user, 'email', None)
        if email:
            return email
        return obj.phone

    def get_profile_pic(self, obj):
        img = getattr(obj.user, 'profile_image', None)
        try:
            url = _clean_text(img.url) if img else None
        except Exception:
            return None
        if not url:
            return None
        request = self.context.get("request")
        if request and isinstance(url, str) and not url.lower().startswith(("http://", "https://")):
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

    def get_private_project(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "id", None) if project else None

    def get_private_project_title(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "title", None) if project else None

    def get_documents(self, obj):
        docs = []
        for d in obj.documents.all().order_by("-uploaded_at"):
            docs.append(
                {
                    "id": d.id,
                    "title": d.title,
                    "description": d.description,
                    "document_type": d.document_type,
                    "document_url": _employee_document_api_url(self.context.get("request"), obj.id, d.id),
                    "status": d.status,
                    "uploaded_at": d.uploaded_at,
                    "updated_at": d.updated_at,
                }
            )
        return docs


    def get_joining_documents(self, obj):
        return []

    def get_documents_submitted_to_admin(self, obj):
        return []

    def get_has_password(self, obj):
        try:
            return obj.user.has_usable_password()
        except Exception:
            return False

    def validate_email(self, value):
        email = (value or "").strip()
        if not email:
            return value
        instance = getattr(self, 'instance', None)
        qs_email = User.objects.filter(email__iexact=email)
        qs_username = User.objects.filter(username__iexact=email)
        if instance and instance.user_id:
            qs_email = qs_email.exclude(id=instance.user_id)
            qs_username = qs_username.exclude(id=instance.user_id)
        if qs_email.exists() or qs_username.exists():
            raise serializers.ValidationError('Email/login already registered.')
        return email

    def validate_employee_id(self, value):
        eid = (value or "").strip()
        if not eid:
            return value
        instance = getattr(self, 'instance', None)
        qs = EmployeeProfile.objects.filter(employee_id__iexact=eid)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Employee ID '{eid}' is already in use by another employee.")
        return eid


    def update(self, instance, validated_data):
        user = getattr(instance, 'user', None)
        if user is None:
            raise serializers.ValidationError({'detail': 'Employee user account is missing.'})

        user_data = validated_data.pop('user', {})
        email = user_data.get('email')
        if isinstance(email, str) and email.strip():
            user.email = email
            user.username = email

        profile_image = user_data.get('profile_image')
        if isinstance(profile_image, UploadedFile):
            user.profile_image = profile_image

        phone = validated_data.get('phone')
        if phone is not None:
            try:
                user.phoneno = phone
            except Exception:
                pass

        name = self.context.get('name')
        if isinstance(name, str) and name.strip():
            parts = name.strip().split(' ', 1)
            user.firstname = parts[0]
            user.lastname = parts[1] if len(parts) > 1 else ''

        password = self.context.get('password')
        if isinstance(password, str) and password:
            user.set_password(password)

        try:
            user.save()
        except IntegrityError as exc:
            raise serializers.ValidationError(_employee_integrity_error_detail(exc))

        return super().update(instance, validated_data)

    def create(self, validated_data):
        user_data = validated_data.pop('user', {})
        email = user_data.get('email')
        profile_image = user_data.get('profile_image')
        name = self.context.get('name') or ''
        password = self.context.get('password')

        parts = str(name).strip().split(' ', 1) if str(name).strip() else ['Employee', '']
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''

        phone = validated_data.get('phone', '') or ''
        username = email if isinstance(email, str) and email.strip() else phone
        try:
            user = User.objects.create_user(
                username=username,
                email=email if isinstance(email, str) and email.strip() else '',
                phoneno=phone,
                password=password or get_random_string(24),
            )
        except IntegrityError as exc:
            raise serializers.ValidationError(_employee_integrity_error_detail(exc))
        if isinstance(profile_image, UploadedFile):
            user.profile_image = profile_image
            user.save()
        user.firstname = first_name
        user.lastname = last_name
        user.save()

        custom_eid = (validated_data.get('employee_id') or '').strip()
        if custom_eid:
            employee_id = custom_eid
        else:
            max_num = 9999
            for eid in EmployeeProfile.objects.filter(employee_id__startswith="DI").values_list("employee_id", flat=True):
                s = str(eid or "")
                digits = s[2:]
                if digits.isdigit():
                    try:
                        max_num = max(max_num, int(digits))
                    except Exception:
                        pass
            employee_id = f"DI{max_num + 1}"

        employee_profile = None
        for _ in range(5):
            try:
                employee_profile = EmployeeProfile.objects.create(
                    user=user,
                    employee_id=employee_id,
                    phone=validated_data.get('phone', ''),
                    designation=validated_data.get('designation', 'Applicant'),
                    qualification=validated_data.get('qualification', ''),
                    employment_type=validated_data.get('employment_type', ''),
                    location=validated_data.get('location', ''),
                    status=validated_data.get('status', 'active'),
                    private_project_id=validated_data.get('current_project_id') or validated_data.get('private_project_id'),
                )
                break
            except Exception:
                max_num += 1
                employee_id = f"DI{max_num + 1}"
        if employee_profile is None:
            try:
                user.delete()
            except Exception:
                pass
            raise serializers.ValidationError("Failed to create employee profile")

        return employee_profile

class EmployeeAdminListSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', required=False)
    login_id = serializers.SerializerMethodField()
    status = serializers.CharField(required=False)
    employee_id = serializers.CharField(read_only=True)
    designation = serializers.CharField(required=False, allow_blank=True)
    private_project = serializers.SerializerMethodField()
    private_project_title = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    profile_pic = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeProfile
        fields = [
            'id',
            'employee_id',
            'login_id',
            'name',
            'email',
            'phone',
            'designation',
            'profile_pic',
            'location',
            'employment_type',
            'qualification',
            'status',
            'is_active',
            'private_project',
            'private_project_title',
            'linkedin_url',
            'created_at',
            'updated_at',
        ]

    def get_name(self, obj):
        first = getattr(obj.user, 'firstname', '') or ''
        last = getattr(obj.user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(obj.user, 'username', '')

    def get_is_active(self, obj):
        return obj.status == 'active'

    def get_login_id(self, obj):
        email = getattr(obj.user, 'email', None)
        if email:
            return email
        return obj.phone

    def get_profile_pic(self, obj):
        img = getattr(obj.user, 'profile_image', None)
        try:
            url = _clean_text(img.url) if img else None
        except Exception:
            return None
        if not url:
            return None
        request = self.context.get("request")
        if request and isinstance(url, str) and not url.lower().startswith(("http://", "https://")):
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

    def get_private_project(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "id", None) if project else None

    def get_private_project_title(self, obj):
        project = _resolve_employee_current_project(obj)
        return getattr(project, "title", None) if project else None

    def get_joining_documents(self, obj):
        return []

    def get_documents_submitted_to_admin(self, obj):
        return []

    def get_has_password(self, obj):
        try:
            return obj.user.has_usable_password()
        except Exception:
            return False

    def validate_email(self, value):
        instance = getattr(self, 'instance', None)
        qs = User.objects.filter(email=value)
        if instance and instance.user_id:
            qs = qs.exclude(id=instance.user_id)
        if qs.exists():
            raise serializers.ValidationError('Email already registered.')
        return value

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        email = user_data.get('email')
        if isinstance(email, str) and email.strip():
            instance.user.email = email
            instance.user.username = email

        profile_image = user_data.get('profile_image')
        if isinstance(profile_image, UploadedFile):
            instance.user.profile_image = profile_image

        phone = validated_data.get('phone')
        if phone is not None:
            try:
                instance.user.phoneno = phone
            except Exception:
                pass

        name = self.context.get('name')
        if isinstance(name, str) and name.strip():
            parts = name.strip().split(' ', 1)
            instance.user.firstname = parts[0]
            instance.user.lastname = parts[1] if len(parts) > 1 else ''

        password = self.context.get('password')
        if isinstance(password, str) and password:
            instance.user.set_password(password)

        instance.user.save()
        return super().update(instance, validated_data)

    def create(self, validated_data):
        user_data = validated_data.pop('user', {})
        email = user_data.get('email')
        profile_image = user_data.get('profile_image')
        name = self.context.get('name') or ''
        password = self.context.get('password')

        parts = str(name).strip().split(' ', 1) if str(name).strip() else ['Employee', '']
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''

        phone = validated_data.get('phone', '') or ''
        username = email if isinstance(email, str) and email.strip() else phone
        user = User.objects.create_user(
            username=username,
            email=email if isinstance(email, str) and email.strip() else '',
            phoneno=phone,
            password=password or get_random_string(24),
        )
        if isinstance(profile_image, UploadedFile):
            user.profile_image = profile_image
            user.save()
        user.firstname = first_name
        user.lastname = last_name
        user.save()

        max_num = 9999
        for eid in EmployeeProfile.objects.filter(employee_id__startswith="DI").values_list("employee_id", flat=True):
            s = str(eid or "")
            digits = s[2:]
            if digits.isdigit():
                try:
                    max_num = max(max_num, int(digits))
                except Exception:
                    pass
        employee_id = f"DI{max_num + 1}"

        employee_profile = None
        for _ in range(5):
            try:
                employee_profile = EmployeeProfile.objects.create(
                    user=user,
                    employee_id=employee_id,
                    phone=validated_data.get('phone', ''),
                    designation=validated_data.get('designation', 'Applicant'),
                    qualification=validated_data.get('qualification', ''),
                    employment_type=validated_data.get('employment_type', ''),
                    location=validated_data.get('location', ''),
                    status=validated_data.get('status', 'active'),
                    private_project_id=validated_data.get('current_project_id') or validated_data.get('private_project_id'),
                )
                break
            except Exception:
                max_num += 1
                employee_id = f"DI{max_num + 1}"
        if employee_profile is None:
            raise serializers.ValidationError("Failed to create employee profile")

        return employee_profile


from account.employee_models import (
    LeaveRequest,
    OvertimeRequest,
    EmployeeDocument,
    CurrentProjectPlan,
    CurrentProjectAssignment,
    CurrentProjectDailyUpdate,
    PrivateProjectPlan,
    PrivateProjectAssignment,
    PrivateProjectDailyUpdate,
    PrivateProjectTicketAssignment,
    EmployeeTicket,
    EmployeeTicketAttachment,
    EmployeeTicketComment,
    EmployeeTicketAssignmentHistory,
    CurrentProjectTicketAssignment,
)

class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.SerializerMethodField()
    total_days = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            'id',
            'employee',
            'employee_id',
            'employee_name',
            'start_date',
            'end_date',
            'total_days',
            'reason',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_employee_name(self, obj):
        first = getattr(obj.employee.user, 'firstname', '') or ''
        last = getattr(obj.employee.user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(obj.employee.user, 'username', '')

    def get_total_days(self, obj):
        start = getattr(obj, 'start_date', None)
        end = getattr(obj, 'end_date', None)
        if not start or not end:
            return None
        try:
            delta = (end - start).days + 1
        except Exception:
            return None
        return delta if delta >= 0 else None


class OvertimeRequestSerializer(serializers.ModelSerializer):
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = OvertimeRequest
        fields = [
            'id',
            'employee',
            'employee_id',
            'employee_name',
            'date',
            'hours',
            'reason',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_employee_name(self, obj):
        first = getattr(obj.employee.user, 'firstname', '') or ''
        last = getattr(obj.employee.user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(obj.employee.user, 'username', '')


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeDocument
        fields = [
            'id',
            'employee',
            'employee_id',
            'employee_name',
            'title',
            'description',
            'document_type',
            'file',
            'file_url',
            'status',
            'uploaded_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'uploaded_at', 'updated_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.file:
            return None
        url = obj.file.url
        if request:
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

    def get_employee_name(self, obj):
        first = getattr(obj.employee.user, 'firstname', '') or ''
        last = getattr(obj.employee.user, 'lastname', '') or ''
        full = f"{first} {last}".strip()
        return full or getattr(obj.employee.user, 'username', '')


def _user_label(user):
    if not user:
        return ""
    first = getattr(user, 'firstname', '') or ''
    last = getattr(user, 'lastname', '') or ''
    full = f"{first} {last}".strip()
    return full or getattr(user, 'username', '') or getattr(user, 'email', '') or ''


def _employee_label(employee):
    if not employee:
        return ""
    return _user_label(getattr(employee, "user", None)) or getattr(employee, "employee_id", "") or str(getattr(employee, "id", ""))


def _ticket_status_to_api(value):
    if value == "open":
        return "pending"
    return value


def _ticket_status_from_api(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"pending", "open"}:
        return "open"
    if text in {"in-progress", "in_progress"}:
        return "in_progress"
    if text in {"resolved"}:
        return "resolved"
    if text in {"closed"}:
        return "closed"
    return value


class EmployeeTicketAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    file = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeTicketAttachment
        fields = ['id', 'file', 'file_url', 'url', 'file_name', 'uploaded_at']
        read_only_fields = ['id', 'file', 'file_url', 'url', 'uploaded_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.file:
            return None
        try:
            url = obj.file.url
        except Exception:
            return None
        if request and isinstance(url, str) and not url.lower().startswith(("http://", "https://")):
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

    def get_url(self, obj):
        return self.get_file_url(obj)

    def get_file(self, obj):
        return self.get_file_url(obj)


class EmployeeTicketCommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()
    author_employee_id = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeTicketComment
        fields = [
            'id',
            'ticket',
            'text',
            'author',
            'author_name',
            'author_employee_id',
            'attachments',
            'can_edit',
            'can_delete',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'author',
            'author_name',
            'author_employee_id',
            'attachments',
            'can_edit',
            'can_delete',
            'created_at',
        ]

    def _can_modify_comment(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None

        if not user or not getattr(user, 'is_authenticated', False):
            return False

        # Admin can modify every comment.
        if (
            getattr(user, 'is_staff', False)
            or getattr(user, 'is_superuser', False)
            or getattr(user, 'is_admin', False)
        ):
            return True

        employee = getattr(user, 'employee_profile', None)

        if not employee:
            return False

        # Only the comment author can modify the comment.
        author_matches = obj.author_id == user.id

        if not author_matches:
            author_employee = getattr(obj, 'author_employee', None)

            author_matches = bool(
                author_employee
                and author_employee.user_id == user.id
            )

        if not author_matches:
            return False

        ticket = getattr(obj, 'ticket', None)

        if not ticket:
            return False

        # Multi-assignee support.
        try:
            if ticket.assignees.filter(pk=employee.pk).exists():
                return True
        except Exception:
            pass

        # Backward compatibility with primary assignee.
        return getattr(ticket, 'assigned_to_id', None) == employee.pk

    def get_can_edit(self, obj):
        return self._can_modify_comment(obj)

    def get_can_delete(self, obj):
        return self._can_modify_comment(obj)

    def get_author(self, obj):
        employee = getattr(obj, "author_employee", None)
        user = getattr(obj, "author", None)

        if employee:
            uid = getattr(user, "id", None) or getattr(employee, "user_id", None) or employee.id
            return {
                "id": uid,
                "employee_profile_id": employee.id,
                "name": _employee_label(employee),
                "email": getattr(
                    getattr(employee, "user", None),
                    "email",
                    ""
                ) or "",
                "employee_id": getattr(
                    employee,
                    "employee_id",
                    ""
                ),
            }

        if user:
            return {
                "id": user.id,
                "name": _user_label(user),
                "employee_id": str(user.id),
            }

        return None

    def get_author_name(self, obj):
        employee = getattr(obj, "author_employee", None)
        user = getattr(obj, "author", None)

        if employee:
            return _employee_label(employee)

        if user:
            return _user_label(user)

        return "Unknown"

    def get_author_employee_id(self, obj):
        employee = getattr(obj, "author_employee", None)
        user = getattr(obj, "author", None)

        if employee:
            return getattr(
                employee,
                "employee_id",
                ""
            ) or ""

        if user:
            return str(user.id)

        return ""

    def get_attachments(self, obj):
        attachments = getattr(obj, "attachments", None)

        if attachments is not None:
            queryset = attachments.all()
        else:
            ticket = getattr(obj, "ticket", None)
            queryset = (
                ticket.attachments.filter(
                    comment__isnull=True
                ).all()
                if ticket
                else []
            )

        return EmployeeTicketAttachmentSerializer(
            queryset,
            many=True,
            context=self.context
        ).data


class EmployeeTicketAssignmentHistorySerializer(serializers.ModelSerializer):
    from_employee = serializers.SerializerMethodField()
    to_employee = serializers.SerializerMethodField()
    by = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeTicketAssignmentHistory
        fields = ['id', 'from_employee', 'to_employee', 'by', 'reason', 'at']
        read_only_fields = ['id', 'at']

    def get_from_employee(self, obj):
        e = getattr(obj, "from_employee", None)
        if not e:
            return None
        return {"id": e.id, "name": _employee_label(e), "email": getattr(getattr(e, "user", None), "email", "") or "", "employee_code": getattr(e, "employee_id", "")}

    def get_to_employee(self, obj):
        e = getattr(obj, "to_employee", None)
        if not e:
            return None
        return {"id": e.id, "name": _employee_label(e), "email": getattr(getattr(e, "user", None), "email", "") or "", "employee_code": getattr(e, "employee_id", "")}

    def get_by(self, obj):
        u = getattr(obj, "by", None)
        if not u:
            return None
        return {"id": u.id, "name": _user_label(u)}


def _get_ticket_project_data(obj):
    if not obj:
        return None

    private_assignment = None
    if hasattr(obj, "private_plan_assignments"):
        private_assignment = (
            obj.private_plan_assignments
            .select_related("plan__project")
            .first()
        )

    if private_assignment and getattr(private_assignment, "plan", None):
        plan = private_assignment.plan
        project = getattr(plan, "project", None)
        if project:
            return {
                "id": project.id,
                "name": (
                    getattr(plan, "project_name", "")
                    or getattr(project, "title", "")
                    or getattr(project, "name", "")
                    or f"Project #{project.id}"
                ),
            }

    current_assignment = None
    if hasattr(obj, "plan_assignments"):
        current_assignment = (
            obj.plan_assignments
            .select_related("plan__project")
            .first()
        )

    if current_assignment and getattr(current_assignment, "plan", None):
        plan = current_assignment.plan
        project = getattr(plan, "project", None)
        if project:
            return {
                "id": project.id,
                "name": (
                    getattr(plan, "project_name", "")
                    or getattr(project, "title", "")
                    or getattr(project, "name", "")
                    or f"Project #{project.id}"
                ),
            }

    return None


class EmployeeTicketListSerializer(serializers.ModelSerializer):
    employee = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    assigned_to_ids = serializers.SerializerMethodField()
    assignees = serializers.SerializerMethodField()
    assigned_by = serializers.SerializerMethodField()
    can_reassign = serializers.SerializerMethodField()
    project = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeTicket
        fields = [
            'id',
            'ticket_number',
            'employee',
            'title',
            'description',
            'status',
            'priority',
            'category',
            'created_at',
            'updated_at',
            'assigned_to',
            'assigned_to_ids',
            'assignees',
            'assigned_by',
            'assigned_at',
            'can_reassign',
            'project',
            'created_by',
        ]
        read_only_fields = ['id', 'ticket_number', 'created_at', 'updated_at', 'created_by']

    def get_employee(self, obj):
        e = getattr(obj, "employee", None)
        if not e:
            return None
        return {"id": e.id, "name": _employee_label(e), "email": getattr(getattr(e, "user", None), "email", "") or "", "employee_code": getattr(e, "employee_id", "")}

    def get_status(self, obj):
        return _ticket_status_to_api(getattr(obj, "status", None))

    def get_assigned_to(self, obj):
        e = getattr(obj, "assigned_to", None)
        if not e:
            return None
        return {"id": e.id, "name": _employee_label(e), "email": getattr(getattr(e, "user", None), "email", "") or "", "employee_code": getattr(e, "employee_id", "")}

    def get_assigned_to_ids(self, obj):
        ids = list(obj.assignees.values_list("id", flat=True))
        if not ids and obj.assigned_to_id:
            ids = [obj.assigned_to_id]
        return ids

    def get_assignees(self, obj):
        employees = list(obj.assignees.select_related("user").all())
        if not employees and obj.assigned_to:
            employees = [obj.assigned_to]

        return [
            {
                "id": employee.id,
                "name": _employee_label(employee),
                "email": getattr(getattr(employee, "user", None), "email", "") or "",
                "employee_code": getattr(employee, "employee_id", ""),
            }
            for employee in employees
        ]

    def get_assigned_by(self, obj):
        u = getattr(obj, "assigned_by", None)
        if not u:
            return None
        return {"id": u.id, "name": _user_label(u)}

    def get_created_by(self, obj):
        u = getattr(obj, "created_by", None)
        if not u:
            return None
        return {
            "id": u.id,
            "username": getattr(u, "username", "") or "",
            "name": _user_label(u),
            "email": getattr(u, "email", "") or "",
            "is_staff": bool(getattr(u, "is_staff", False) or getattr(u, "is_superuser", False) or getattr(u, "is_admin", False)),
        }

    def get_can_reassign(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        return bool(user and getattr(user, "is_authenticated", False) and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) or getattr(user, "is_admin", False)))

    def get_project(self, obj):
        return _get_ticket_project_data(obj)


class EmployeeTicketDetailSerializer(serializers.ModelSerializer):
    status = serializers.CharField(required=False)
    employee_info = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    assigned_to_ids = serializers.SerializerMethodField()
    assignees = serializers.SerializerMethodField()
    assigned_by = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    project = serializers.SerializerMethodField()
    project_assignments = serializers.SerializerMethodField()   

    employee = serializers.PrimaryKeyRelatedField(
        queryset=EmployeeProfile.objects.all(),
        required=False,
        allow_null=True,
    )

    project_id = serializers.IntegerField(   
        required=False,
        allow_null=True,
        write_only=True,
    )

    assigned_to_id = serializers.PrimaryKeyRelatedField(
        source="assigned_to",
        queryset=EmployeeProfile.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )

    # Canonical multi-assignee write field.
    assignee_ids = serializers.PrimaryKeyRelatedField(
        source="assignees",
        queryset=EmployeeProfile.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
    )

    ticket_number = serializers.CharField(read_only=True)
    attachments = EmployeeTicketAttachmentSerializer(many=True, read_only=True)
    assignment_history = EmployeeTicketAssignmentHistorySerializer(many=True, read_only=True)
    comments = EmployeeTicketCommentSerializer(many=True, read_only=True)

    class Meta:
        model = EmployeeTicket
        fields = [
            "id",
            "ticket_number",
            "employee",
            "employee_info",
            "title",
            "description",
            "status",
            "priority",
            "category",
            "created_by",
            "assigned_to",
            "assigned_to_id",
            "assignee_ids",
            "assigned_to_ids",
            "assignees",
            "reason",
            "assigned_by",
            "assigned_at",
            "attachments",
            "assignment_history",
            "comments",
            "created_at",
            "updated_at",
            "project",
            "project_id",
            "project_assignments",
        ]
        read_only_fields = [
            "id",
            "ticket_number",
            "created_at",
            "updated_at",
            "created_by",
            "assigned_by",
            "assigned_at",
            "attachments",
            "assignment_history",
            "assigned_to_ids",
            "assignees",
        ]

    def validate_status(self, value):
        return _ticket_status_from_api(value)

    def validate(self, attrs):
        if not self.instance:
            project_id = attrs.get("project_id")
            employee = attrs.get("employee")
            assignees = attrs.get("assignees")
            assigned_to = attrs.get("assigned_to")

            is_project_mode = project_id not in (None, "", "null")

            if is_project_mode:
                candidates = list(assignees or [])
                if not candidates and assigned_to:
                    candidates = [assigned_to]
                if not candidates and employee:
                    candidates = [employee]
                if not candidates:
                    raise serializers.ValidationError({
                        "assignee_ids": "Please select at least one employee for the project ticket."
                    })
            else:
                candidates = list(assignees or [])
                if not employee and not candidates and not assigned_to:
                    raise serializers.ValidationError({
                        "employee": "Please select an employee for the direct employee ticket."
                    })
        return attrs

    def _set_assignment_state(self, instance, employees, user, reason, old_ids=None, old_primary=None):
        employees = list(employees or [])
        new_ids = {employee.id for employee in employees}
        old_ids = set(old_ids or [])

        instance.assignees.set(employees)
        instance.assigned_to = employees[0] if employees else None
        instance.assigned_by = user if employees else None
        instance.assigned_at = timezone.now() if employees else None
        instance.save(
            update_fields=[
                "assigned_to",
                "assigned_by",
                "assigned_at",
                "updated_at",
            ]
        )

        for employee in employees:
            if employee.id not in old_ids:
                EmployeeTicketAssignmentHistory.objects.create(
                    ticket=instance,
                    from_employee=old_primary,
                    to_employee=employee,
                    by=user,
                    reason=reason,
                )

    def create(self, validated_data):
        reason = str(validated_data.pop("reason", "") or "").strip()
        project_id = validated_data.pop("project_id", None)

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        # assignee_ids is mapped to "assignees" by source="assignees".
        assignee_candidates = validated_data.pop("assignees", None)

        # Backward-compatible single-assignee creation.
        if (
            assignee_candidates is None
            and validated_data.get("assigned_to") is not None
        ):
            assignee_candidates = [validated_data.get("assigned_to")]

        assigned_to = validated_data.get("assigned_to")
        employees = list(assignee_candidates or [])

        # ---------------------------------------------------------
        # Resolve the selected project plan.
        # ---------------------------------------------------------
        private_plan = None
        current_plan = None

        if project_id not in (None, "", "null"):
            try:
                private_plan = (
                    PrivateProjectPlan.objects
                    .filter(project_id=int(project_id))
                    .first()
                )
            except (ValueError, TypeError):
                private_plan = None

            if private_plan is None:
                try:
                    current_plan = (
                        CurrentProjectPlan.objects
                        .filter(project_id=int(project_id))
                        .first()
                    )
                except (ValueError, TypeError):
                    current_plan = None

            if private_plan is None and current_plan is None:
                raise serializers.ValidationError({
                    "project_id": "Selected project does not have a project plan."
                })

            plan = private_plan or current_plan

            # Only employees already assigned to the selected project
            # can receive a project ticket.
            project_employee_ids = set(
                plan.assignments.values_list("employee_id", flat=True)
            )

            invalid_employees = [
                employee.id
                for employee in employees
                if employee.id not in project_employee_ids
            ]

            if invalid_employees:
                raise serializers.ValidationError({
                    "assignee_ids":
                        "One or more selected employees are not assigned to this project."
                })

            if not employees:
                if validated_data.get("employee"):
                    employees = [validated_data["employee"]]
                else:
                    raise serializers.ValidationError({
                        "assignee_ids":
                            "Please select at least one employee for the project ticket."
                    })

            # EmployeeTicket still requires one employee. Use the first
            # selected project employee as the primary employee.
            if not validated_data.get("employee"):
                validated_data["employee"] = employees[0]
        else:
            # DIRECT EMPLOYEE MODE:
            # No project selected. Link directly to employee without project assignments.
            if validated_data.get("employee") and not employees:
                employees = [validated_data["employee"]]
            elif employees and not validated_data.get("employee"):
                validated_data["employee"] = employees[0]
            elif not validated_data.get("employee") and assigned_to:
                validated_data["employee"] = assigned_to
                if not employees:
                    employees = [assigned_to]

            if not validated_data.get("employee"):
                raise serializers.ValidationError({
                    "employee": "Please select an employee for the direct employee ticket."
                })

        # ---------------------------------------------------------
        # Create ticket.
        # ---------------------------------------------------------
        instance = super().create(validated_data)

        # ---------------------------------------------------------
        # Keep the existing normal ticket assignment workflow.
        # ---------------------------------------------------------
        if employees:
            self._set_assignment_state(
                instance,
                employees,
                user,
                reason,
            )
        elif assigned_to is not None:
            self._set_assignment_state(
                instance,
                [assigned_to],
                user,
                reason,
            )
        elif validated_data.get("employee"):
            self._set_assignment_state(
                instance,
                [validated_data["employee"]],
                user,
                reason,
            )

        # ---------------------------------------------------------
        # Link project -> ticket -> employee using existing bridge models.
        # ONLY in project mode!
        # ---------------------------------------------------------
        if project_id not in (None, "", "null"):
            if private_plan is not None:
                for employee in employees:
                    PrivateProjectTicketAssignment.objects.get_or_create(
                        plan=private_plan,
                        employee=employee,
                        ticket=instance,
                    )
            elif current_plan is not None:
                for employee in employees:
                    CurrentProjectTicketAssignment.objects.get_or_create(
                        plan=current_plan,
                        employee=employee,
                        ticket=instance,
                    )

        return instance

    def update(self, instance, validated_data):
        reason = str(validated_data.pop("reason", "") or "").strip()
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        assignee_candidates = validated_data.pop("assignees", None)
        old_ids = list(instance.assignees.values_list("id", flat=True))
        old_primary = getattr(instance, "assigned_to", None)

        # If an old client only sends assigned_to_id, keep it synchronized with M2M.
        if assignee_candidates is None and "assigned_to" in validated_data:
            assignee_candidates = [validated_data.get("assigned_to")] if validated_data.get("assigned_to") else []

        instance = super().update(instance, validated_data)

        if assignee_candidates is not None:
            self._set_assignment_state(
                instance,
                assignee_candidates,
                user,
                reason,
                old_ids=old_ids,
                old_primary=old_primary,
            )

        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["status"] = _ticket_status_to_api(data.get("status"))
        return data

    def get_employee_info(self, obj):
        e = getattr(obj, "employee", None)
        if not e:
            return None
        return {
            "id": e.id,
            "name": _employee_label(e),
            "email": getattr(getattr(e, "user", None), "email", "") or "",
            "employee_code": getattr(e, "employee_id", ""),
        }

    def get_assigned_to(self, obj):
        e = getattr(obj, "assigned_to", None)
        if not e:
            return None
        return {
            "id": e.id,
            "name": _employee_label(e),
            "email": getattr(getattr(e, "user", None), "email", "") or "",
            "employee_code": getattr(e, "employee_id", ""),
        }

    def get_assigned_to_ids(self, obj):
        ids = list(obj.assignees.values_list("id", flat=True))
        if not ids and obj.assigned_to_id:
            ids = [obj.assigned_to_id]
        return ids

    def get_assignees(self, obj):
        employees = list(obj.assignees.select_related("user").all())
        if not employees and obj.assigned_to:
            employees = [obj.assigned_to]

        return [
            {
                "id": employee.id,
                "name": _employee_label(employee),
                "email": getattr(getattr(employee, "user", None), "email", "") or "",
                "employee_code": getattr(employee, "employee_id", ""),
            }
            for employee in employees
        ]

    def get_assigned_by(self, obj):
        u = getattr(obj, "assigned_by", None)
        if not u:
            return None
        return {"id": u.id, "name": _user_label(u)}

    def get_created_by(self, obj):
        u = getattr(obj, "created_by", None)
        if not u:
            return None
        return {
            "id": u.id,
            "username": getattr(u, "username", "") or "",
            "name": _user_label(u),
            "email": getattr(u, "email", "") or "",
            "is_staff": bool(getattr(u, "is_staff", False) or getattr(u, "is_superuser", False) or getattr(u, "is_admin", False)),
        }

    def get_project(self, obj):
        return _get_ticket_project_data(obj)


    def get_project_assignments(self, obj):
        result = []

        private_assignments = (
            obj.private_plan_assignments
            .select_related("employee__user", "plan__project")
            .all()
        )

        for assignment in private_assignments:
            result.append({
                "id": assignment.id,
                "project_id": assignment.plan.project_id,
                "employee_id": assignment.employee_id,
                "employee_code": getattr(
                    assignment.employee,
                    "employee_id",
                    "",
                ),
                "employee_name": _employee_label(
                    assignment.employee
                ),
            })

        current_assignments = (
            obj.plan_assignments
            .select_related("employee__user", "plan__project")
            .all()
        )

        for assignment in current_assignments:
            result.append({
                "id": assignment.id,
                "project_id": assignment.plan.project_id,
                "employee_id": assignment.employee_id,
                "employee_code": getattr(
                    assignment.employee,
                    "employee_id",
                    "",
                ),
                "employee_name": _employee_label(
                    assignment.employee
                ),
            })

        return result


class PrivateProjectDailyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivateProjectDailyUpdate
        fields = ['id', 'date', 'text', 'created_at']
        read_only_fields = ['id', 'created_at']


class PrivateProjectAssignmentSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=EmployeeProfile.objects.all(), required=True)
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    name = serializers.SerializerMethodField()
    daily_updates = PrivateProjectDailyUpdateSerializer(many=True, required=False)

    class Meta:
        model = PrivateProjectAssignment
        fields = [
            'id',
            'employee',
            'employee_id',
            'name',
            'designation',
            'start_date',
            'end_date',
            'work',
            'status',
            'admin_comment',
            'employee_comment',
            'daily_updates',
        ]
        read_only_fields = ['id', 'employee_id']

    def get_name(self, obj):
        e = getattr(obj, "employee", None)
        if not e:
            return ""
        return _employee_label(e)


class PrivateProjectTicketAssignmentSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(
        queryset=EmployeeProfile.objects.all(),
        required=True,
    )

    employee_id = serializers.CharField(
        source="employee.employee_id",
        read_only=True,
    )

    ticket = serializers.PrimaryKeyRelatedField(
        queryset=EmployeeTicket.objects.all(),
        required=True,
    )

    ticket_number = serializers.CharField(
        source="ticket.ticket_number",
        read_only=True,
    )

    ticket_title = serializers.CharField(
        source="ticket.title",
        read_only=True,
    )

    ticket_status = serializers.CharField(
        source="ticket.status",
        read_only=True,
    )

    ticket_priority = serializers.CharField(
        source="ticket.priority",
        read_only=True,
    )

    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = PrivateProjectTicketAssignment

        fields = [
            "id",
            "ticket",
            "ticket_number",
            "ticket_title",
            "ticket_status",
            "ticket_priority",
            "employee",
            "employee_id",
            "employee_name",
            "assign_date",
            "expire_date",
        ]

        read_only_fields = [
            "id",
            "employee_id",
            "ticket_number",
            "ticket_title",
            "ticket_status",
            "ticket_priority",
            "employee_name",
        ]

    def get_employee_name(self, obj):
        employee = getattr(obj, "employee", None)

        if not employee:
            return ""

        return _employee_label(employee)


class PrivateProjectPlanSerializer(serializers.ModelSerializer):
    employees = PrivateProjectAssignmentSerializer(
        source="assignments",
        many=True,
        required=False,
    )

    assignments = PrivateProjectAssignmentSerializer(
        many=True,
        required=False,
    )

    ticket_assignments = PrivateProjectTicketAssignmentSerializer(
        many=True,
        required=False,
    )

    tickets = serializers.SerializerMethodField()

    class Meta:
        model = PrivateProjectPlan

        fields = [
            "id",
            "project",
            "start_date",
            "end_date",
            "timeline",
            "project_name",
            "project_description",
            "employees",
            "assignments",
            "ticket_assignments",
            "tickets",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "tickets",
            "updated_at",
        ]

    def get_tickets(self, obj):
        if not obj:
            return []
        bridge_assignments = list(
            obj.ticket_assignments.select_related("employee", "employee__user").all()
        )
        ticket_ids = list({ta.ticket_id for ta in bridge_assignments if ta.ticket_id})
        if not ticket_ids:
            return []
        bridge_emps_by_ticket = {}
        for ta in bridge_assignments:
            if ta.ticket_id and ta.employee:
                bridge_emps_by_ticket.setdefault(ta.ticket_id, []).append(ta.employee)

        from account.employee_models import EmployeeTicket
        tickets_qs = (
            EmployeeTicket.objects.filter(pk__in=ticket_ids)
            .select_related("assigned_to", "assigned_to__user", "employee", "employee__user")
            .prefetch_related("assignees", "assignees__user")
            .order_by("-updated_at", "-id")
        )
        def _emp_info(ep):
            if not ep:
                return None
            return {
                "id": ep.id,
                "name": _employee_label(ep),
                "employee_code": getattr(ep, "employee_id", ""),
            }

        res = []
        for t in tickets_qs:
            emp_map = {}
            for e in bridge_emps_by_ticket.get(t.pk, []):
                if e and e.id:
                    emp_map[e.id] = e
            for e in t.assignees.all():
                if e and e.id:
                    emp_map[e.id] = e
            if t.assigned_to and t.assigned_to.id:
                emp_map[t.assigned_to.id] = t.assigned_to

            assignees_list = list(emp_map.values())
            assigned_ids = list(emp_map.keys())

            res.append({
                "id": t.pk,
                "ticket_number": t.ticket_number or "",
                "title": t.title or "",
                "description": t.description or "",
                "status": t.status or "",
                "priority": t.priority or "",
                "employee": _emp_info(t.employee),
                "assigned_to": _emp_info(t.assigned_to),
                "assigned_employee_ids": assigned_ids,
                "assignees": [
                    {
                        "id": e.id,
                        "name": _employee_label(e),
                        "employee_code": getattr(e, "employee_id", ""),
                    }
                    for e in assignees_list
                ],
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else (t.created_at.isoformat() if t.created_at else None),
            })
        return res


    def update(self, instance, validated_data):
        assignments_payload = validated_data.pop(
            "assignments",
            None,
        )

        validated_data.pop(
            "employees",
            None,
        )

        ticket_assignments_payload = validated_data.pop(
            "ticket_assignments",
            None,
        )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        request = self.context.get("request")
        user = getattr(request, "user", None)

        is_admin = bool(
            user
            and getattr(user, "is_authenticated", False)
            and (
                getattr(user, "is_staff", False)
                or getattr(user, "is_superuser", False)
                or getattr(user, "is_admin", False)
            )
        )

        # ---------------------------------------------------------
        # PROJECT EMPLOYEE ASSIGNMENTS
        # ---------------------------------------------------------

        if assignments_payload is not None:
            keep_assignment_ids = []

            for row in assignments_payload:
                if not isinstance(row, dict):
                    continue

                employee = row.get("employee")

                if employee in (None, "", "null"):
                    continue

                employee_obj = (
                    employee
                    if isinstance(employee, EmployeeProfile)
                    else None
                )

                if employee_obj is None:
                    try:
                        employee_obj = EmployeeProfile.objects.get(
                            pk=int(
                                getattr(
                                    employee,
                                    "pk",
                                    employee,
                                )
                            )
                        )
                    except Exception:
                        continue

                assignment_id = row.get("id")

                assignment = None

                if assignment_id not in (
                    None,
                    "",
                    "null",
                ):
                    try:
                        assignment = (
                            PrivateProjectAssignment.objects
                            .filter(
                                plan=instance,
                                pk=int(assignment_id),
                            )
                            .first()
                        )
                    except Exception:
                        assignment = None

                if assignment is None:
                    assignment, _ = (
                        PrivateProjectAssignment.objects
                        .get_or_create(
                            plan=instance,
                            employee=employee_obj,
                        )
                    )

                for field in [
                    "designation",
                    "start_date",
                    "end_date",
                    "work",
                    "status",
                    "admin_comment",
                    "employee_comment",
                ]:
                    if field in row:
                        setattr(
                            assignment,
                            field,
                            row.get(field),
                        )

                assignment.save()
                keep_assignment_ids.append(
                    assignment.id
                )

            (
                PrivateProjectAssignment.objects
                .filter(plan=instance)
                .exclude(id__in=keep_assignment_ids)
                .delete()
            )

        # ---------------------------------------------------------
        # PROJECT TICKET ASSIGNMENTS
        # ---------------------------------------------------------

        if is_admin and ticket_assignments_payload is not None:

            if not isinstance(
                ticket_assignments_payload,
                list,
            ):
                raise serializers.ValidationError(
                    {
                        "ticket_assignments":
                            "Expected a list."
                    }
                )

            keep_ticket_assignment_ids = []

            for row in ticket_assignments_payload:

                if not isinstance(row, dict):
                    continue

                ticket = row.get("ticket")
                employee = row.get("employee")

                if ticket in (
                    None,
                    "",
                    "null",
                ):
                    continue

                if employee in (
                    None,
                    "",
                    "null",
                ):
                    continue

                # Resolve ticket
                ticket_obj = (
                    ticket
                    if isinstance(ticket, EmployeeTicket)
                    else None
                )

                if ticket_obj is None:
                    try:
                        ticket_obj = (
                            EmployeeTicket.objects
                            .get(
                                pk=int(
                                    getattr(
                                        ticket,
                                        "pk",
                                        ticket,
                                    )
                                )
                            )
                        )
                    except Exception:
                        continue

                # Resolve employee
                employee_obj = (
                    employee
                    if isinstance(
                        employee,
                        EmployeeProfile,
                    )
                    else None
                )

                if employee_obj is None:
                    try:
                        employee_obj = (
                            EmployeeProfile.objects
                            .get(
                                pk=int(
                                    getattr(
                                        employee,
                                        "pk",
                                        employee,
                                    )
                                )
                            )
                        )
                    except Exception:
                        continue

                # IMPORTANT:
                # Employee must belong to this project.
                if not (
                    PrivateProjectAssignment.objects
                    .filter(
                        plan=instance,
                        employee=employee_obj,
                    )
                    .exists()
                ):
                    raise serializers.ValidationError(
                        {
                            "ticket_assignments":
                                f"Employee {employee_obj.employee_id} "
                                f"is not assigned to this project."
                        }
                    )

                assignment_id = row.get("id")

                ticket_assignment = None

                if assignment_id not in (
                    None,
                    "",
                    "null",
                ):
                    try:
                        ticket_assignment = (
                            PrivateProjectTicketAssignment.objects
                            .filter(
                                plan=instance,
                                pk=int(assignment_id),
                            )
                            .first()
                        )
                    except Exception:
                        ticket_assignment = None

                if ticket_assignment is None:
                    ticket_assignment, _ = (
                        PrivateProjectTicketAssignment.objects
                        .get_or_create(
                            plan=instance,
                            employee=employee_obj,
                            ticket=ticket_obj,
                        )
                    )

                if "assign_date" in row:
                    ticket_assignment.assign_date = (
                        row.get("assign_date")
                    )

                if "expire_date" in row:
                    ticket_assignment.expire_date = (
                        row.get("expire_date")
                    )

                ticket_assignment.save()

                keep_ticket_assignment_ids.append(
                    ticket_assignment.id
                )

            (
                PrivateProjectTicketAssignment.objects
                .filter(plan=instance)
                .exclude(
                    id__in=keep_ticket_assignment_ids
                )
                .delete()
            )

        return instance
    
class CurrentProjectDailyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrentProjectDailyUpdate
        fields = ['id', 'date', 'text', 'created_at']
        read_only_fields = ['id', 'created_at']


class CurrentProjectAssignmentSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=EmployeeProfile.objects.all(), required=True)
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    name = serializers.SerializerMethodField()
    daily_updates = CurrentProjectDailyUpdateSerializer(many=True, required=False)

    class Meta:
        model = CurrentProjectAssignment
        fields = [
            'id',
            'employee',
            'employee_id',
            'name',
            'designation',
            'start_date',
            'end_date',
            'work',
            'status',
            'admin_comment',
            'employee_comment',
            'daily_updates',
        ]
        read_only_fields = ['id', 'employee_id']

    def get_name(self, obj):
        e = getattr(obj, "employee", None)
        if not e:
            return ""
        return _employee_label(e)


class CurrentProjectTicketAssignmentSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=EmployeeProfile.objects.all(), required=True)
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.SerializerMethodField()
    ticket = serializers.PrimaryKeyRelatedField(queryset=EmployeeTicket.objects.all(), required=True)
    ticket_number = serializers.CharField(source='ticket.ticket_number', read_only=True)
    ticket_title = serializers.CharField(source='ticket.title', read_only=True)
    ticket_status = serializers.CharField(source='ticket.status', read_only=True)
    ticket_priority = serializers.CharField(source='ticket.priority', read_only=True)

    class Meta:
        model = CurrentProjectTicketAssignment
        fields = [
            'id',
            'ticket',
            'ticket_number',
            'ticket_title',
            'ticket_status',
            'ticket_priority',
            'employee',
            'employee_id',
            'employee_name',
            'assign_date',
            'expire_date',
        ]
        read_only_fields = [
            'id',
            'employee_id',
            'ticket_number',
            'ticket_title',
            'ticket_status',
            'ticket_priority',
            'employee_name',
        ]

    def get_employee_name(self, obj):
        e = getattr(obj, "employee", None)
        if not e:
            return ""
        return _employee_label(e)


class CurrentProjectPlanSerializer(serializers.ModelSerializer):
    employees = CurrentProjectAssignmentSerializer(source='assignments', many=True, required=False)
    assignments = CurrentProjectAssignmentSerializer(many=True, required=False)
    ticket_assignments = CurrentProjectTicketAssignmentSerializer(many=True, required=False)
    tickets = serializers.SerializerMethodField()

    class Meta:
        model = CurrentProjectPlan
        fields = [
            "id",
            "project",
            "start_date",
            "end_date",
            "timeline",
            "project_name",
            "project_description",
            "employees",
            "assignments",
            "ticket_assignments",
            "tickets",
            "updated_at",
        ]
        read_only_fields = ['id', 'tickets', 'updated_at']

    def get_tickets(self, obj):
        if not obj:
            return []
        bridge_assignments = list(
            obj.ticket_assignments.select_related("employee", "employee__user").all()
        )
        ticket_ids = list({ta.ticket_id for ta in bridge_assignments if ta.ticket_id})
        if not ticket_ids:
            return []
        bridge_emps_by_ticket = {}
        for ta in bridge_assignments:
            if ta.ticket_id and ta.employee:
                bridge_emps_by_ticket.setdefault(ta.ticket_id, []).append(ta.employee)

        from account.employee_models import EmployeeTicket
        tickets_qs = (
            EmployeeTicket.objects.filter(pk__in=ticket_ids)
            .select_related("assigned_to", "assigned_to__user", "employee", "employee__user")
            .prefetch_related("assignees", "assignees__user")
            .order_by("-updated_at", "-id")
        )
        def _emp_info(ep):
            if not ep:
                return None
            return {
                "id": ep.id,
                "name": _employee_label(ep),
                "employee_code": getattr(ep, "employee_id", ""),
            }

        res = []
        for t in tickets_qs:
            emp_map = {}
            for e in bridge_emps_by_ticket.get(t.pk, []):
                if e and e.id:
                    emp_map[e.id] = e
            for e in t.assignees.all():
                if e and e.id:
                    emp_map[e.id] = e
            if t.assigned_to and t.assigned_to.id:
                emp_map[t.assigned_to.id] = t.assigned_to

            assignees_list = list(emp_map.values())
            assigned_ids = list(emp_map.keys())

            res.append({
                "id": t.pk,
                "ticket_number": t.ticket_number or "",
                "title": t.title or "",
                "description": t.description or "",
                "status": t.status or "",
                "priority": t.priority or "",
                "employee": _emp_info(t.employee),
                "assigned_to": _emp_info(t.assigned_to),
                "assigned_employee_ids": assigned_ids,
                "assignees": [
                    {
                        "id": e.id,
                        "name": _employee_label(e),
                        "employee_code": getattr(e, "employee_id", ""),
                    }
                    for e in assignees_list
                ],
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else (t.created_at.isoformat() if t.created_at else None),
            })
        return res

    def update(self, instance, validated_data):
        assignments_payload = validated_data.pop('assignments', None)
        assignments_payload = validated_data.pop('employees', assignments_payload)
        ticket_assignments_payload = validated_data.pop('ticket_assignments', None)

        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        is_admin = bool(
            user
            and getattr(user, 'is_authenticated', False)
            and (
                getattr(user, 'is_staff', False)
                or getattr(user, 'is_superuser', False)
                or getattr(user, 'is_admin', False)
            )
        )
        employee_profile = (
            getattr(user, 'employee_profile', None) if user and getattr(user, 'is_authenticated', False) else None
        )

        for attr, value in validated_data.items():
            if attr == 'timeline' and not is_admin:
                continue
            setattr(instance, attr, value)
        instance.save()

        if is_admin and ticket_assignments_payload is not None:
            if not isinstance(ticket_assignments_payload, list):
                raise serializers.ValidationError({"ticket_assignments": "Expected a list"})

            seen = set()
            keep_ids = []
            for row in ticket_assignments_payload:
                if not isinstance(row, dict):
                    continue
                ticket = row.get('ticket')
                employee = row.get('employee')
                if ticket in (None, '', 'null') or employee in (None, '', 'null'):
                    continue
                key = (
                    str(getattr(ticket, "pk", ticket)),
                    str(getattr(employee, "pk", employee)),
                )
                if key in seen:
                    raise serializers.ValidationError({"ticket_assignments": "Duplicate ticket assignment in request"})
                seen.add(key)

                ticket_obj = ticket if isinstance(ticket, EmployeeTicket) else None
                if ticket_obj is None:
                    try:
                        ticket_obj = EmployeeTicket.objects.get(pk=int(getattr(ticket, "pk", ticket)))
                    except Exception:
                        continue

                employee_obj = employee if isinstance(employee, EmployeeProfile) else None
                if employee_obj is None:
                    try:
                        employee_obj = EmployeeProfile.objects.get(pk=int(getattr(employee, "pk", employee)))
                    except Exception:
                        continue

                assignment_id = row.get('id')
                ta = None
                if assignment_id not in (None, '', 'null'):
                    try:
                        ta = CurrentProjectTicketAssignment.objects.filter(plan=instance, pk=int(assignment_id)).first()
                    except Exception:
                        ta = None
                if ta is None:
                    ta, _ = CurrentProjectTicketAssignment.objects.get_or_create(plan=instance, employee=employee_obj, ticket=ticket_obj)

                if 'assign_date' in row:
                    ta.assign_date = row.get('assign_date')
                if 'expire_date' in row:
                    ta.expire_date = row.get('expire_date')
                ta.save()
                keep_ids.append(ta.id)

            CurrentProjectTicketAssignment.objects.filter(plan=instance).exclude(id__in=keep_ids).delete()

        if assignments_payload is None:
            return instance

        if not isinstance(assignments_payload, list):
            return instance

        keep_assignment_ids = []
        for row in assignments_payload:
            if not isinstance(row, dict):
                continue

            employee = row.get('employee')
            if employee in (None, '', 'null'):
                continue
            employee_obj = None
            if isinstance(employee, EmployeeProfile):
                employee_obj = employee
            else:
                try:
                    employee_obj = EmployeeProfile.objects.get(pk=int(getattr(employee, "pk", employee)))
                except Exception:
                    employee_obj = None
            if employee_obj is None:
                continue

            assignment, _ = CurrentProjectAssignment.objects.get_or_create(plan=instance, employee=employee_obj)
            if not assignment.designation:
                assignment.designation = getattr(employee_obj, "designation", "") or ""

            if is_admin:
                for f in ('designation', 'start_date', 'end_date', 'work', 'status', 'admin_comment', 'employee_comment'):
                    if f in row:
                        setattr(assignment, f, row.get(f))
            else:
                if employee_profile and employee_obj.id == employee_profile.id:
                    if 'employee_comment' in row and row.get('employee_comment') is not None:
                        assignment.employee_comment = row.get('employee_comment')

            assignment.save()
            keep_assignment_ids.append(assignment.id)

            if not is_admin:
                daily_updates = row.get('daily_updates')
                if isinstance(daily_updates, list):
                    for du in daily_updates:
                        if not isinstance(du, dict):
                            continue
                        text = du.get('text')
                        date = du.get('date')
                        if not text or not date:
                            continue
                        if not employee_profile or employee_obj.id != employee_profile.id:
                            continue
                        CurrentProjectDailyUpdate.objects.create(assignment=assignment, date=date, text=text)

        if is_admin:
            CurrentProjectAssignment.objects.filter(plan=instance).exclude(id__in=keep_assignment_ids).delete()

        return instance







