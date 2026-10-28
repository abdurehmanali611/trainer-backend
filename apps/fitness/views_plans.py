from django.db.models import Q
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth import IsTrainerRole

from .models import DietPlan, Exercise, WorkoutPlan
from .serializers import (
    DietPlanSerializer,
    ExerciseSerializer,
    WorkoutPlanSerializer,
)


class ExerciseListView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = ExerciseSerializer

    def get_queryset(self):
        qs = Exercise.objects.filter(Q(trainer__isnull=True) | Q(trainer=self.request.user))
        group = self.request.query_params.get("group")
        if group and group != "All":
            qs = qs.filter(muscle_group=group)
        exercise_type = self.request.query_params.get("type")
        if exercise_type and exercise_type != "all":
            qs = qs.filter(exercise_type=exercise_type)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        return qs.order_by("name")

    def perform_create(self, serializer):
        serializer.save(trainer=self.request.user)


class ExerciseDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = ExerciseSerializer

    def get_queryset(self):
        qs = Exercise.objects.filter(Q(trainer=self.request.user) | Q(trainer__isnull=True))
        if self.request.method != "GET":
            # Shared base-library entries are read-only; trainers may only
            # edit or delete the exercises they created themselves.
            qs = qs.filter(trainer=self.request.user)
        return qs


class WorkoutPlanListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = WorkoutPlanSerializer

    def get_queryset(self):
        qs = WorkoutPlan.objects.filter(trainer=self.request.user)
        client_id = self.request.query_params.get("client")
        if client_id == "templates":
            qs = qs.filter(client__isnull=True)
        elif client_id:
            qs = qs.filter(client_id=client_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(trainer=self.request.user)


class WorkoutPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = WorkoutPlanSerializer

    def get_queryset(self):
        return WorkoutPlan.objects.filter(trainer=self.request.user)


class WorkoutPlanAssignView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        from .models import Client, PlannedExercise, WorkoutDay

        template = generics.get_object_or_404(
            WorkoutPlan, pk=pk, trainer=request.user, client__isnull=True
        )
        client = generics.get_object_or_404(Client, pk=request.data.get("client_id"), trainer=request.user)
        plan = WorkoutPlan.objects.create(
            trainer=request.user, client=client, name=template.name
        )
        for day in template.days.all():
            new_day = WorkoutDay.objects.create(
                plan=plan, day_name=day.day_name, order=day.order
            )
            PlannedExercise.objects.bulk_create(
                PlannedExercise(
                    day=new_day,
                    exercise_id=ex.exercise_id,
                    sets=ex.sets,
                    reps=ex.reps,
                    target_weight=ex.target_weight,
                    rest_seconds=ex.rest_seconds,
                    order=ex.order,
                )
                for ex in day.exercises.all()
            )
        return Response(WorkoutPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class DietPlanListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = DietPlanSerializer

    def get_queryset(self):
        qs = DietPlan.objects.filter(trainer=self.request.user)
        client_id = self.request.query_params.get("client")
        if client_id == "templates":
            qs = qs.filter(client__isnull=True)
        elif client_id:
            qs = qs.filter(client_id=client_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(trainer=self.request.user)


class DietPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = DietPlanSerializer

    def get_queryset(self):
        return DietPlan.objects.filter(trainer=self.request.user)


class DietPlanAssignView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        from .models import Client, Meal, MealItem

        template = generics.get_object_or_404(
            DietPlan, pk=pk, trainer=request.user, client__isnull=True
        )
        client = generics.get_object_or_404(Client, pk=request.data.get("client_id"), trainer=request.user)
        plan = DietPlan.objects.create(
            trainer=request.user, client=client, name=template.name,
            daily_calories=template.daily_calories, protein=template.protein,
            carbs=template.carbs, fats=template.fats,
        )
        for meal in template.meals.all():
            new_meal = Meal.objects.create(
                diet_plan=plan, name=meal.name, time=meal.time, order=meal.order
            )
            MealItem.objects.bulk_create(
                MealItem(
                    meal=new_meal, name=item.name, calories=item.calories,
                    protein=item.protein, carbs=item.carbs, fats=item.fats,
                    order=item.order,
                )
                for item in meal.items.all()
            )
        return Response(DietPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class AISuggestPlanView(APIView):
    """AI plan suggestions — provider decided later; backend stub for now."""

    permission_classes = [IsTrainerRole]

    def post(self, request):
        return Response(
            {
                "status": "stub",
                "message": "AI provider not connected yet. The suggestion pipeline will "
                "generate workout/nutrition plans from the client profile here.",
                "input": {
                    "client_id": request.data.get("client_id"),
                    "goal": request.data.get("goal", ""),
                },
                "suggestion": None,
            }
        )
