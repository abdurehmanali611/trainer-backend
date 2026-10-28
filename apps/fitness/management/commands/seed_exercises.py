from django.core.management.base import BaseCommand

from apps.fitness.models import Exercise

BASE_EXERCISES = [
    ("Barbell Bench Press", "Chest", "intermediate", "Barbell", 4, "8-10", 90,
     "Lie on bench, lower bar to mid-chest, press up until arms extended."),
    ("Incline Dumbbell Press", "Chest", "intermediate", "Dumbbell", 3, "10-12", 75,
     "Press dumbbells from upper chest on an incline bench."),
    ("Push Ups", "Chest", "beginner", "Bodyweight", 3, "12-20", 60,
     "Standard push-up keeping body in a straight line."),
    ("Cable Fly", "Chest", "beginner", "Cable Machine", 3, "12-15", 60,
     "Bring handles together in front of chest with slight elbow bend."),
    ("Deadlift", "Back", "advanced", "Barbell", 4, "5-6", 120,
     "Hinge at hips, keep bar close, stand tall with locked hips and knees."),
    ("Pull Ups", "Back", "intermediate", "Bodyweight", 4, "6-10", 90,
     "Hang from bar, pull chin above bar, lower with control."),
    ("Barbell Row", "Back", "intermediate", "Barbell", 4, "8-10", 90,
     "Bent over, pull bar to lower chest/upper abdomen."),
    ("Lat Pulldown", "Back", "beginner", "Cable Machine", 3, "10-12", 60,
     "Pull bar to upper chest while keeping torso upright."),
    ("Back Extension", "Back", "beginner", "Bodyweight", 3, "12-15", 45,
     "Hinge forward at hips then extend back to neutral spine."),
    ("Barbell Squat", "Legs", "advanced", "Barbell", 4, "6-8", 120,
     "Bar on upper back, squat until thighs parallel, drive up."),
    ("Leg Press", "Legs", "beginner", "Cable Machine", 3, "10-12", 90,
     "Push platform away with feet, lower under control."),
    ("Romanian Deadlift", "Legs", "intermediate", "Barbell", 3, "8-10", 90,
     "Slight knee bend, hinge hips back, feel hamstring stretch."),
    ("Walking Lunges", "Legs", "beginner", "Dumbbell", 3, "12 each", 60,
     "Step forward and lower back knee toward ground."),
    ("Leg Curl", "Legs", "beginner", "Cable Machine", 3, "12-15", 45,
     "Curl heels toward glutes lying face down."),
    ("Overhead Press", "Shoulders", "intermediate", "Barbell", 4, "8-10", 90,
     "Press bar from shoulders to overhead lockout."),
    ("Lateral Raise", "Shoulders", "beginner", "Dumbbell", 3, "12-15", 45,
     "Raise dumbbells out to sides with slight elbow bend."),
    ("Front Raise", "Shoulders", "beginner", "Dumbbell", 3, "10-12", 45,
     "Raise dumbbells in front of you to shoulder height."),
    ("Rear Delt Fly", "Shoulders", "beginner", "Dumbbell", 3, "12-15", 45,
     "Bent over, raise arms out to sides squeezing rear delts."),
    ("Barbell Curl", "Arms", "beginner", "Barbell", 3, "10-12", 60,
     "Curl bar up keeping elbows pinned to sides."),
    ("Dumbbell Curl", "Arms", "beginner", "Dumbbell", 3, "10-12", 60,
     "Curl dumbbells alternately or together."),
    ("Tricep Pushdown", "Arms", "beginner", "Cable Machine", 3, "12-15", 45,
     "Push bar down keeping elbows fixed at sides."),
    ("Skull Crusher", "Arms", "intermediate", "Barbell", 3, "8-10", 75,
     "Lower bar to forehead, extend arms back up."),
    ("Hammer Curl", "Arms", "beginner", "Dumbbell", 3, "10-12", 45,
     "Neutral-grip curl targeting brachialis."),
    ("Plank", "Core", "beginner", "Bodyweight", 3, "45-60s", 45,
     "Hold a straight-body plank on forearms."),
    ("Hanging Leg Raise", "Core", "intermediate", "Bodyweight", 3, "10-15", 60,
     "Hang from bar, raise legs to hip height or above."),
    ("Cable Crunch", "Core", "intermediate", "Cable Machine", 3, "12-15", 45,
     "Kneel, crunch torso down toward floor."),
    ("Russian Twist", "Core", "beginner", "Bodyweight", 3, "20 total", 45,
     "Seated, rotate torso side to side with feet off floor."),
    ("Treadmill Walk", "Cardio", "beginner", "Bodyweight", 1, "20-30 min", 0,
     "Brisk walking to warm up or cool down."),
    ("Cycling", "Cardio", "beginner", "Bodyweight", 1, "20-30 min", 0,
     "Steady-state cycling at conversational pace."),
    ("Jump Rope", "Cardio", "intermediate", "Bodyweight", 3, "2 min", 60,
     "Boxer-step or two-foot bounce, stay light on feet."),
    ("Burpees", "Cardio", "intermediate", "Bodyweight", 3, "10-15", 60,
     "Squat, kick back to plank, push-up, jump up."),
    ("Kettlebell Swing", "Cardio", "intermediate", "Kettlebell", 4, "15-20", 60,
     "Hinge and snap hips to swing bell to chest height."),
    ("Dumbbell Shrug", "Back", "beginner", "Dumbbell", 3, "12-15", 45,
     "Shrug shoulders straight up toward ears."),
    ("Face Pull", "Shoulders", "beginner", "Cable Machine", 3, "15-20", 45,
     "Pull rope to face, elbows high, external rotation at end."),
]


class Command(BaseCommand):
    help = "Seed the shared exercise library"

    def handle(self, *args, **options):
        created = 0
        for name, group, diff, equip, sets, reps, rest, desc in BASE_EXERCISES:
            _, was_created = Exercise.objects.get_or_create(
                name=name,
                trainer=None,
                defaults={
                    "muscle_group": group,
                    "difficulty": diff,
                    "equipment": equip,
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": rest,
                    "description": desc,
                },
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} exercises ({len(BASE_EXERCISES)} total)."))
