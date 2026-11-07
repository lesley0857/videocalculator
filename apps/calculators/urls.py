from django.urls import path
from .views import (
    CalculatorPlaceholderView,
    ClipPlannerCalculateApiView,
    NarrationCalculateApiView,
    TalkingFlyerClipPlannerTestView,
    TalkingFlyerNarrationTestView,
)

app_name = 'calculators'

urlpatterns = [
    path('', CalculatorPlaceholderView.as_view(), name='index'),
    path(
        'talking-flyer/narration-test/',
        TalkingFlyerNarrationTestView.as_view(),
        name='talking-flyer-narration-test',
    ),
    path(
        'talking-flyer/narration-test/calculate/',
        NarrationCalculateApiView.as_view(),
        name='narration-calculate-api',
    ),
    path(
        'talking-flyer/clip-planner-test/',
        TalkingFlyerClipPlannerTestView.as_view(),
        name='talking-flyer-clip-planner-test',
    ),
    path(
        'talking-flyer/clip-planner-test/calculate/',
        ClipPlannerCalculateApiView.as_view(),
        name='clip-planner-calculate-api',
    ),
]
