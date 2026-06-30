from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from account import views
from .views import LoginView
from .views import BlogAdminViewSet
from .api import (
    AdminDashboardAPI,
    ProjectAPI,
    ProjectDraftAPI,
    EmployeeProjectsAPI,
    ProjectMembershipsAPI,
    ProjectMembershipDetailAPI,
    GalleryAPI, GalleryDetailAPI,
    ProductAPI, ProductGalleryAPI,
    ServiceAPI,
    ServiceBySlugAPI,
    ServiceExploreSubsectionAPI,
    GisServiceAPI,
    GisServiceBySlugAPI,
    GisServiceExploreSubsectionAPI,
    TestimonialAPI,
    TestimonialDetailAPI,
    ImageUploadAPI,
    AdminImageUploadAPI,
    CompanyCertificateAPI,
)
from .employee_admin_views import (
    EmployeeDetailAPI,
    EmployeeDocumentFileAPI,
    EmployeeDocumentDetailAPI,
    EmployeeDocumentsAPI,
    EmployeeTicketDetailAPI,
    EmployeeTicketReassignAPI,
    EmployeeTicketBulkAssignAPI,
    EmployeeTicketsAPI,
    EmployeeTicketsStatsAPI,
    EmployeeTicketCommentsAPI,
    EmployeeTicketCommentsFlatAPI,
    EmployeeSetPasswordAPI,
    LeaveBalanceAPI,
    EmployeeMeAPI,
    EmployeesAPI,
    LeaveRequestDetailAPI,
    LeaveRequestsAPI,
    OvertimeRequestDetailAPI,
    OvertimeRequestsAPI,
)
from .private_project_views import (
    PrivateProjectsAPI,
    PrivateProjectDetailAPI,
    PrivateProjectPlanAPI,
    PrivateProjectPlanAssignmentsAPI,
    PrivateProjectPlanAssignmentAPI,
    PrivateProjectDailyUpdatesAPI,
)
from .dashboard_views import DashboardSummaryAPI
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView,
    TeamMemberViewSet,
    BlogViewSet,
    BlogListAPI,
    BlogDetailAPI,
    BlogCategoryViewSet,
    BlogCategoryAdminViewSet,
    BlogCommentListCreateAPI,
    BlogCommentAdminViewSet,
)


router = DefaultRouter()
router.register(r'team', TeamMemberViewSet , basename='team')
router.register(r'blog', BlogViewSet , basename='blog')
router.register(r'blogs', BlogViewSet , basename='blogs')
router.register(r"admin/blogs", BlogAdminViewSet, basename="admin-blogs")
router.register(r"blog-categories", BlogCategoryViewSet, basename="blog-categories")
router.register(r"admin/blog-categories", BlogCategoryAdminViewSet, basename="admin-blog-categories")
router.register(r"admin/blog-comments", BlogCommentAdminViewSet, basename="admin-blog-comments")
app_name = 'account'

urlpatterns = [
    path("api/blogs/", BlogListAPI.as_view(), name="public-blog-list"),
    path("api/blogs/<slug:slug>/", BlogDetailAPI.as_view(), name="public-blog-detail"),
    path("api/blogs/<slug:slug>/comments/", BlogCommentListCreateAPI.as_view(), name="public-blog-comments"),
    path("api/blogs", BlogListAPI.as_view(), name="public-blog-list-noslash"),
    path("api/blogs/<slug:slug>", BlogDetailAPI.as_view(), name="public-blog-detail-noslash"),
    path("api/blogs/<slug:slug>/comments", BlogCommentListCreateAPI.as_view(), name="public-blog-comments-noslash"),
    
      
    # Testimonials
    path('api/testimonials/', TestimonialAPI.as_view(), name='testimonial-list'),
    path('api/testimonials/<int:pk>/', TestimonialDetailAPI.as_view(), name='testimonial-detail'),

        # Services (existing IT services endpoint)
    path('api/services/', ServiceAPI.as_view(), name='service-list'),
    path('api/services/<str:pk>/', ServiceAPI.as_view(), name='service-detail'),
    path('api/services/by-slug/<slug:slug>/', ServiceBySlugAPI.as_view(), name='service-by-slug'),
    path('api/services/by-slug/<slug:slug>', ServiceBySlugAPI.as_view(), name='service-by-slug-noslash'),
    path('api/services/<slug:service_slug>/<slug:sub_slug>/', ServiceExploreSubsectionAPI.as_view(), name='service-explore-subsection'),
    path('api/services/<slug:service_slug>/<slug:sub_slug>', ServiceExploreSubsectionAPI.as_view(), name='service-explore-subsection-noslash'),
    re_path(r'^api/services/(?P<service_slug>[-\w]+)/(?P<sub_slug>[-\w]+)/?$', ServiceExploreSubsectionAPI.as_view(), name='service-explore-subsection-regex'),
    re_path(r'^api//services/(?P<service_slug>[-\w]+)/(?P<sub_slug>[-\w]+)/?$', ServiceExploreSubsectionAPI.as_view(), name='service-explore-subsection-double-slash'),

    path('api/employees', EmployeesAPI.as_view(), name='employees-noslash'),
    path('api/employees/', EmployeesAPI.as_view(), name='employees'),
    path('api/employees/<int:pk>', EmployeeDetailAPI.as_view(), name='employee-detail-noslash'),
    path('api/employees/<int:pk>/', EmployeeDetailAPI.as_view(), name='employee-detail'),
    path('api/employees/<int:pk>/documents/<int:doc_id>/', EmployeeDocumentFileAPI.as_view(), name='employee-document-file'),
    path('api/employees/<int:pk>/set-password', EmployeeSetPasswordAPI.as_view(), name='employee-set-password-noslash'),
    path('api/employees/<int:pk>/set-password/', EmployeeSetPasswordAPI.as_view(), name='employee-set-password'),
    path('api/leave-requests', LeaveRequestsAPI.as_view(), name='leave-requests-noslash'),
    path('api/leave-requests/', LeaveRequestsAPI.as_view(), name='leave-requests'),
    path('api/leave-requests/<int:pk>', LeaveRequestDetailAPI.as_view(), name='leave-request-detail-noslash'),
    path('api/leave-requests/<int:pk>/', LeaveRequestDetailAPI.as_view(), name='leave-request-detail'),
    path('api/overtime-requests', OvertimeRequestsAPI.as_view(), name='overtime-requests-noslash'),
    path('api/overtime-requests/', OvertimeRequestsAPI.as_view(), name='overtime-requests'),
    path('api/overtime-requests/<int:pk>', OvertimeRequestDetailAPI.as_view(), name='overtime-request-detail-noslash'),
    path('api/overtime-requests/<int:pk>/', OvertimeRequestDetailAPI.as_view(), name='overtime-request-detail'),
    path('api/employee-documents', EmployeeDocumentsAPI.as_view(), name='employee-documents-noslash'),
    path('api/employee-documents/', EmployeeDocumentsAPI.as_view(), name='employee-documents'),
    path('api/employee-documents/<int:pk>', EmployeeDocumentDetailAPI.as_view(), name='employee-document-detail-noslash'),
    path('api/employee-documents/<int:pk>/', EmployeeDocumentDetailAPI.as_view(), name='employee-document-detail'),
    path('api/employee-tickets', EmployeeTicketsAPI.as_view(), name='employee-tickets-noslash'),
    path('api/employee-tickets/', EmployeeTicketsAPI.as_view(), name='employee-tickets'),
    path('api/employee-tickets/stats/', EmployeeTicketsStatsAPI.as_view(), name='employee-tickets-stats'),
    path('api/employee-tickets/bulk-assign/', EmployeeTicketBulkAssignAPI.as_view(), name='employee-tickets-bulk-assign'),
    path('api/employee-tickets/<int:pk>/comments/', EmployeeTicketCommentsAPI.as_view(), name='employee-ticket-comments'),
    path('api/employee-tickets/undefined', EmployeeTicketsAPI.as_view(), name='employee-tickets-undefined-noslash'),
    path('api/employee-tickets/undefined/', EmployeeTicketsAPI.as_view(), name='employee-tickets-undefined'),
    path('api/employee-tickets/null', EmployeeTicketsAPI.as_view(), name='employee-tickets-null-noslash'),
    path('api/employee-tickets/null/', EmployeeTicketsAPI.as_view(), name='employee-tickets-null'),
    path('api/employee-tickets/<int:pk>/reassign/', EmployeeTicketReassignAPI.as_view(), name='employee-ticket-reassign'),
    path('api/employee-tickets/<int:pk>', EmployeeTicketDetailAPI.as_view(), name='employee-ticket-detail-noslash'),
    path('api/employee-tickets/<int:pk>/', EmployeeTicketDetailAPI.as_view(), name='employee-ticket-detail'),
    path('api/employee-ticket-comments/', EmployeeTicketCommentsFlatAPI.as_view(), name='employee-ticket-comments-flat'),
    path('api/ticket-comments/', EmployeeTicketCommentsFlatAPI.as_view(), name='ticket-comments-flat'),
    path('api/employee/me/', EmployeeMeAPI.as_view(), name='employee-me'),
    path('api/employees/me', EmployeeMeAPI.as_view(), name='employees-me-noslash'),
    path('api/employees/me/', EmployeeMeAPI.as_view(), name='employees-me'),
    path('api/leave-balance', LeaveBalanceAPI.as_view(), name='leave-balance-noslash'),
    path('api/leave-balance/', LeaveBalanceAPI.as_view(), name='leave-balance'),

    path('api/gis-services/', GisServiceAPI.as_view(), name='gis-service-list'),
    path('api/gis-services/<str:pk>/', GisServiceAPI.as_view(), name='gis-service-detail'),
    path('api/gis-services/by-slug/<slug:slug>/', GisServiceBySlugAPI.as_view(), name='gis-service-by-slug'),
    path('api/gis-services/by-slug/<slug:slug>', GisServiceBySlugAPI.as_view(), name='gis-service-by-slug-noslash'),
    path('api/gis-services/<slug:service_slug>/<slug:sub_slug>/', GisServiceExploreSubsectionAPI.as_view(), name='gis-service-explore-subsection'),
    path('api/gis-services/<slug:service_slug>/<slug:sub_slug>', GisServiceExploreSubsectionAPI.as_view(), name='gis-service-explore-subsection-noslash'),
    re_path(r'^api/gis-services/(?P<service_slug>[-\w]+)/(?P<sub_slug>[-\w]+)/?$', GisServiceExploreSubsectionAPI.as_view(), name='gis-service-explore-subsection-regex'),
    re_path(r'^api//gis-services/(?P<service_slug>[-\w]+)/(?P<sub_slug>[-\w]+)/?$', GisServiceExploreSubsectionAPI.as_view(), name='gis-service-explore-subsection-double-slash'),
    # Admin Dashboard
    path('api/admin/dashboard/', AdminDashboardAPI.as_view(), name='admin-dashboard'),

    path('api/upload-image/', ImageUploadAPI.as_view(), name='upload-image'),
    path('api/admin/upload-image/', AdminImageUploadAPI.as_view(), name='admin-upload-image'),
    path('api/admin/blogs/upload/', AdminImageUploadAPI.as_view(), name='admin-blog-upload-image'),
    
    # Projects
    path('api/projects/', ProjectAPI.as_view(), name='project-list'),
    path('api/projects/new/', ProjectDraftAPI.as_view(), name='project-draft'),
    path('api/projects/<int:pk>/', ProjectAPI.as_view(), name='project-detail'),
    path('api/employees/projects', EmployeeProjectsAPI.as_view(), name='employee-projects-noslash'),
    path('api/employees/projects/', EmployeeProjectsAPI.as_view(), name='employee-projects'),
    path('api/employees/me/projects', EmployeeProjectsAPI.as_view(), name='employees-me-projects-noslash'),
    path('api/employees/me/projects/', EmployeeProjectsAPI.as_view(), name='employees-me-projects'),
    path('api/employees/projects/new/', ProjectDraftAPI.as_view(), name='employee-project-draft'),
    path('api/employees/projects/<int:pk>', EmployeeProjectsAPI.as_view(), name='employee-project-detail-noslash'),
    path('api/employees/projects/<int:pk>/', EmployeeProjectsAPI.as_view(), name='employee-project-detail'),
    path('api/project-memberships', ProjectMembershipsAPI.as_view(), name='project-memberships-noslash'),
    path('api/project-memberships/', ProjectMembershipsAPI.as_view(), name='project-memberships'),
    path('api/project-memberships/<int:pk>', ProjectMembershipDetailAPI.as_view(), name='project-membership-detail-noslash'),
    path('api/project-memberships/<int:pk>/', ProjectMembershipDetailAPI.as_view(), name='project-membership-detail'),

    path('api/private-projects/', PrivateProjectsAPI.as_view(), name='private-projects-list'),
    path('api/private-projects/<int:pk>/', PrivateProjectDetailAPI.as_view(), name='private-projects-detail'),
    path('api/private-projects/<int:pk>/plan/', PrivateProjectPlanAPI.as_view(), name='private-projects-plan'),
    path('api/private-projects/<int:pk>/plan/assignments/', PrivateProjectPlanAssignmentsAPI.as_view(), name='private-projects-plan-assignments'),
    path('api/private-projects/<int:pk>/plan/assignments/<int:assignment_id>/', PrivateProjectPlanAssignmentAPI.as_view(), name='private-projects-plan-assignment'),
    path('api/private-projects/<int:pk>/plan/assignments/<int:assignment_id>/daily-updates/', PrivateProjectDailyUpdatesAPI.as_view(), name='private-projects-plan-daily-updates'),
    path('api/dashboard/summary/', DashboardSummaryAPI.as_view(), name='dashboard-summary'),
    
    # Gallery
    path('api/gallery/', GalleryAPI.as_view(), name='gallery-list'),
    path('api/gallery/<int:pk>/', GalleryDetailAPI.as_view(), name='gallery-detail'),
    
    # ✅ PRODUCT ENDPOINTS - These are CRITICAL
    path('api/products/', ProductAPI.as_view(), name='product-list'),
    path('api/products/<int:pk>/', ProductAPI.as_view(), name='product-detail'),
    
    # Product Gallery
    path('api/products/gallery/', ProductGalleryAPI.as_view(), name='product-gallery-list'),
    
    # Certificates
    path('api/certificates/', CompanyCertificateAPI.as_view(), name='certificate-list'),
    path('api/certificates/<int:pk>/', CompanyCertificateAPI.as_view(), name='certificate-detail'),
    path('api/products/gallery/<int:gallery_pk>/', ProductGalleryAPI.as_view(), name='product-gallery-detail'),
    path('api/products/<int:product_pk>/gallery/', ProductGalleryAPI.as_view(), name='product-specific-gallery'),

    # ✅ EMPLOYEE AUTHENTICATION WITH OTP
    path('api/employee/', include('account.employee_urls')),

    # -------- REGULAR ACCOUNT VIEWS --------
    path('alreadyauthenticated/', views.alreadyAuthenticated, name="alreadyAuthenticated"),
    path("mail", views.mail, name='mail'),
    path('register/', views.register_view, name="register"),
    path('registration/', views.registration2_view, name="registration"),
    path('registrationdone/', views.registrationdone_view, name="registrationdone"),
    path('login/', views.login_view, name="login"),
    path('sendotp/', views.sendotp_view, name="send_otp"),
    path('registeremployee/', views.employeeregister_view, name="registeremployee"),
    path('contactus/', views.contact_view, name="contactusview"),
    path('registrationsuccess/', views.registrationsuccess_view, name="registersuccess"),
    path('logout/', views.logout_view, name="logout"),
    path('api/logout/', views.logout_view, name='api-logout'),
    path('requestnewpassword/', views.requestnewpassword_view, name="requestnewpassword"),

    path('password_reset/done/',
         auth_views.PasswordResetCompleteView.as_view(template_name='account/password_reset_done.html'),
         name='password_reset_done'),

    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),

    path('password_reset/',
         auth_views.PasswordResetView.as_view(template_name='account/password_reset_form.html'),
         name='password_reset'),

    path('reset/done/',
         auth_views.PasswordResetCompleteView.as_view(template_name='account/password_reset_complete.html'),
         name='password_reset_complete'),

    path('api/login/', LoginView.as_view(), name='login'),
    path('api/', include(router.urls)),
]

# Add static files
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Add static files
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
