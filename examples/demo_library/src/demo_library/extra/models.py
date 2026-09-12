"""One model, so the second app label has something for the router to route."""

from django.db import models


class ExtraRecord(models.Model):
    """A row that must land in the demolib database, like its sibling app's."""

    note = models.CharField(max_length=100)

    def __str__(self):
        return self.note
