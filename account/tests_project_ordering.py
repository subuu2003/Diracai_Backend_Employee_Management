from django.test import TestCase

from account.models import Project
from account.serializers import ProjectSerializer


class ProjectOrderingTests(TestCase):
    def make_project(self, title, sort_order):
        return Project.objects.create(
            title=title,
            category="mobile",
            status="planned",
            sortOrder=sort_order,
        )

    def ordered_titles(self):
        return list(
            Project.objects.order_by("sortOrder", "-created_at", "pk")
            .values_list("title", flat=True)
        )

    def test_moving_third_project_to_second_shifts_the_rest(self):
        first = self.make_project("First", 0)
        second = self.make_project("Second", 1)
        third = self.make_project("Third", 2)

        # The UI's Position #2 is stored internally at zero-based index 1.
        serializer = ProjectSerializer(third, data={"sortOrder": 2}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        self.assertEqual(self.ordered_titles(), ["First", "Third", "Second"])
        self.assertEqual(
            list(Project.objects.order_by("sortOrder").values_list("sortOrder", flat=True)),
            [0, 1, 2],
        )
        self.assertEqual(Project.objects.get(pk=first.pk).sortOrder, 0)
        self.assertEqual(Project.objects.get(pk=second.pk).sortOrder, 2)

    def test_reorder_repairs_duplicate_and_gapped_positions(self):
        first = self.make_project("First", 0)
        second = self.make_project("Second", 20)
        third = self.make_project("Third", 20)

        serializer = ProjectSerializer(first, data={"sortOrder": 3}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        self.assertEqual(self.ordered_titles(), ["Third", "Second", "First"])
        self.assertEqual(
            list(Project.objects.order_by("sortOrder").values_list("sortOrder", flat=True)),
            [0, 1, 2],
        )

    def test_new_project_without_a_position_is_appended(self):
        self.make_project("First", 0)
        self.make_project("Second", 1)

        serializer = ProjectSerializer(data={"title": "Third", "category": "mobile", "status": "planned"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        self.assertEqual(self.ordered_titles(), ["First", "Second", "Third"])

    def test_position_one_inserts_a_project_at_the_top(self):
        self.make_project("First", 0)
        self.make_project("Second", 1)

        serializer = ProjectSerializer(
            data={"title": "New first", "category": "mobile", "status": "planned", "sortOrder": 1}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        self.assertEqual(self.ordered_titles(), ["New first", "First", "Second"])
