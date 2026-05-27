from django.contrib import admin
from django.urls import path,include
from home import views


app_name = 'home'


urlpatterns = [

#react app

path("",views.reactapp,name='home'),

path("about/",views.reactapp,name="tgrwa_about"),

path("news/",views.reactapp,name="tgrwa_news"),

path("contactus/",views.reactapp,name="tgrwa_contacus"),

path("resident/blogs/",views.reactapp,name="tgrwa_blogs"),

path("resident/notices/",views.reactapp,name="tgrwa_notices"),

path("resident/memberregistration/",views.reactapp,name="tgrwa_memberregistration"),

path("tgrwamembers123/",views.reactapp,name="tgrwa_members"),

path("createaccount/",views.reactapp,name="create_account"),

path("app/dashboard/general/exams/",views.reactapp,name="exams"),

path("app/dashboard/general/oneexamdetail/",views.reactapp,name="one exam detail"),

path("app/account/userprofile/", views.reactapp,name="userprofile"),

path("takethistest/<int:gk>/<int:pk>/",views.reactappPkGk,name="take this test"),

#path("new",views.newindex,name='homeNew'),
#path("team/",views.newindexteam,name='homeNewTeam'),

#path("team/bibhutiparida/",views.bibhutiparida,name='bibhutiparida'),

#path("team/rasmitasahoo/",views.rasmitasahoo,name='rasmitasahoo'),

#path("team/bibhuprasadmahakud/",views.bibhuprasadmahakud,name='bibhuprasadmahakud'),

#path("team/ipsitpanda/",views.ipsitpanda,name='ipsitpanda'),

#path("team/jackysingla/",views.jackysingla,name='jackysingla'),

#path("team/reetasingla/",views.reetasingla,name='reetasingla'),

#path("team/kiran/",views.kiran,name='kiran'),

#path("team/debaprasadmahakud/",views.debaprasadmahakud,name='debaprasadmahakud'),


#path("demoteacher/",views.demoteacher,name='demoteacher'),

#path("demostudent/",views.demostudent,name='demostudent'),

#path("demomanager/",views.demomanager,name='demomanager'),

#path("demoinstitute/",views.demoinstitute,name='demoinstitute'),

#path("careeredr/",views.careeredr,name='careeratedr'),

#path("careeredr/apply/",views.applyjob,name='applyjob'),












# react application modules/ sections





path("react",views.reactapp,name='reactapp'),

path("createaccount/",views.reactapp,name='redirect0'),




path("dashboard/general/courses/",views.reactapp,name='redirect_courses'),
path("dashboard/general/classes/",views.reactapp,name='redirect_classes'),
path("dashboard/general/exams/",views.reactapp,name='redirect_exams'),
path("dashboard/general/notices/",views.reactapp,name='redirect_notices'),
path("dashboard/general/meetings/",views.reactapp,name='redirect_meetings'),
path("dashboard/general/meetings/<int:pk>/",views.reactappPar,name='redirect_Onemeeting'),


path("dashboard/generalchat/",views.reactapp,name='redirect_generalchat'),


path("video/<str:meetingroomstring>/",views.reactappvideomeet, name='redirect_videoApp'),




path("course/summary/",views.reactapp,name='redirect_course_summary'),
path("course/chat/",views.reactapp,name='redirect_course_chat'),




path("dashboard/subject/",views.reactapp,name='redirect2'),
path("dashboard/news/",views.reactapp,name='redirect3'),



path("messages/chat/",views.reactapp,name='redirect4'),
path("messages/email/",views.reactapp,name='redirect5'),
path("messages/tickets/",views.reactapp,name='redirect6'),



path("account/userprofile/",views.reactapp,name='redirect5'),
path("account/settings/",views.reactapp,name='redirect6'),
path("account/courses/",views.reactapp,name='redirect7'),


path("class/overview/",views.reactapp,name='redirect8'),
path("class/detail/",views.reactapp,name='redirect9'),
path("class/specifics/",views.reactapp,name='redirect10'),







#home app
#path("privacypolicy",views.privacypolicy,name='privacypolicy'),
#path("joinus",views.joinus,name='joinus'),
#path("joinusscienceanalystI",views.joinusscienceanalystI,name='joinusscienceanalystI'),
#path("joinusscienceanalystII",views.joinusscienceanalystII,name='joinusscienceanalystII'),






#path("contactinfo",views.contactinfo,name='contactinfo'),










    # ─── Site Configuration API ───────────────────────────────────────
    path("api/site-config/", views.SiteConfigPublicView.as_view(), name="site-config-public"),
    path("api/site-config/update/", views.SiteConfigAdminView.as_view(), name="site-config-admin"),

    # ─── Hero Video Library API ───────────────────────────────────────
    path("api/hero-videos/", views.HeroVideoListCreateView.as_view(), name="hero-videos-list"),
    path("api/hero-videos/<int:pk>/", views.HeroVideoDetailView.as_view(), name="hero-videos-detail"),

]






