from django.contrib import admin
from .models import Epic, Sprint, Status, Task, Tag, Ticket, TaskTag

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'status', 'priority', 'due_date')
    list_filter = ('project', 'status', 'priority')
    search_fields = ('title', 'description')

admin.site.register(Epic)
admin.site.register(Sprint)
admin.site.register(Status)
admin.site.register(Tag)
admin.site.register(Ticket)
admin.site.register(TaskTag)
# Register your models here.
