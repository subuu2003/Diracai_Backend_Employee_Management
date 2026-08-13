
from pathlib import Path
from datetime import timedelta
import os

#import wordpress_api

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-uczo%0a!buj4$0n(6@3tyd#3!5@vkwcwc*0rlw6(urb0j4f@aj'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['.tgrwa.in','64.227.149.67','localhost','127.0.0.1','192.168.29.12']

 
#BASE_URL = "http://192.168.29.12:8000"
BASE_URL = "http://127.0.0.1:8000"# development
#BASE_URL ="https://tgrwa.in"  #production

#The above lines needs to be changed accordingly in production and developmentenvironment


DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB



AUTH_USER_MODEL = 'account.Account'
# AUTHENTICATION_BACKENDS = (
#     'django.contrib.auth.backends.AllowAllUsersModelBackend',
#     'account.backends.CaseInsensitiveModelBackend',
#     )

AUTHENTICATION_BACKENDS = (
    'account.backends.CaseInsensitiveModelBackend',  # your fixed backend
    'django.contrib.auth.backends.ModelBackend',     # fallback
)



# Application definition

INSTALLED_APPS = [
    'notice',
    'account.apps.AccountConfig',
    'accountAPIs.apps.AccountapisConfig',
    'home.apps.HomeConfig',
    'onlineregistration',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    'corsheaders',
    'storages',
    'Vehicles',
    'drf_spectacular',
    #'django_extensions',
    # 'rest_framework',
   

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
CORS_ALLOW_ALL_ORIGINS = True 

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR,"templates"),'/home/sammy/myprojectdir/dashboard/templates',os.path.join(BASE_DIR,"build")],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WP_URL = 'http://your-wordpress-app.com/'
BLOG_POSTS_PER_PAGE = 5



WSGI_APPLICATION = 'myproject.wsgi.application'

ASGI_APPLICATION = 'myproject.asgi.application'

# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases


DATABASES = { 
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'myproject',
        'USER': 'diracai',
        'PASSWORD': '1234',
        'HOST': '127.0.0.1',   # IMPORTANT
        'PORT': '5432',
    } 
}




# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}



LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

ALWAYS_UPLOAD_FILES_TO_AWS=True

#This means you are uploding to AWS even when running locally


#if BASE_URL=="http://127.0.0.1:8000":#http://webapp.diracai.com

if ALWAYS_UPLOAD_FILES_TO_AWS:    
   AWS_ACCESS_KEY_ID='UCW66UXZOVY3QVYQLSEK'
   AWS_SECRET_ACCESS_KEY='TJi4SulSCtEU5RlHWsKkOpFoL0Qo/qVf5JB6Dcg8rWk'
   AWS_STORAGE_BUCKET_NAME='edrspace'
   AWS_S3_ENDPOINT_URL='https://sgp1.digitaloceanspaces.com'
   AWS_QUERYSTRING_AUTH = False
   AWS_DEFAULT_ACL = 'public-read'
   AWS_S3_OBJECT_PARAMETERS = {
      'CacheControl': 'max-age=86400',
   }
   AWS_LOCATION='edrcontainer1'
   STATIC_URL = 'https://%s/%s/'%(AWS_S3_ENDPOINT_URL,AWS_LOCATION)
   STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
   DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'




#twillio credentials to send SMS to phone
ACCOUNT_SID="AC95ed97b175076fb59b269d019a51fa67"
AUTH_TOKEN="ea5bc54822e20cd39c6bb2e23c639267"



#to be used if you load files locally
if not ALWAYS_UPLOAD_FILES_TO_AWS:
   STATIC_URL = '/static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'




STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
    os.path.join(BASE_DIR, 'media'),
   # os.path.join(BASE_DIR,'build/static')
]



#STATIC_ROOT = os.path.join(BASE_DIR, 'static_cdn')
MEDIA_ROOT = os.path.join(BASE_DIR, 'media_cdn')

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'account.authentication.CookieJWTAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    "DEFAULT_THROTTLE_RATES": {
        "blog_comments": "10/min",
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'DiracAI API',
    'DESCRIPTION': 'DiracAI Backend API Documentation',
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}





# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
#EMAIL_HOST_PASSWORD = 'Bibhu12345^'
#EMAIL_HOST_PASSWORD = 'yjnadnopluupwics'
#if DEBUG:
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

#https://myaccount.google.com/lesssecureapps
#https://accounts.google.com/b/0/displayunlockcaptcha
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = '587'
EMAIL_HOST_USER = 'dicelpip@gmail.com'
EMAIL_HOST_PASSWORD = 'mihnrnehsdftdopa'
DEFAULT_FROM_EMAIL = 'dicelpip@gmail.com'
CONTACT_EMAIL = 'contact@diracai.com'
EMAIL_USE_TLS = True

# ========== CORS SETTINGS ==========
# Allow all origins for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Specific allowed origins (optional)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000", 
    "http://127.0.0.1:8000",
    "http://192.168.29.12:8000",
    "https://diracai.com",
]

# Allowed methods
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET', 
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Allowed headers
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]



SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60000),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=50),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer', 'JWT'),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}












