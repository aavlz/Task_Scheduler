from django.contrib import admin

from .models import MCPServer, MCPTool, MCPToolExecution


@admin.register(MCPServer)
class MCPServerAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')


@admin.register(MCPTool)
class MCPToolAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'server', 'is_active')


@admin.register(MCPToolExecution)
class MCPToolExecutionAdmin(admin.ModelAdmin):
    list_display = ('user', 'tool_slug', 'success', 'created_at')
    list_filter = ('tool_slug', 'success')
