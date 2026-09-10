"""One model, so there is something for the router to route."""

from django.db import models


class GameRecord(models.Model):
    """A row that must land in the demogame database and nowhere else."""

    note = models.CharField(max_length=100)

    def __str__(self):
        return self.note
