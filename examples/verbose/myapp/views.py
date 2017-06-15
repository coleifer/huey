from django.shortcuts import render
# Create your views here.

from .tasks import hardtask

tasks_list = []


def get_status_of_tasks():
    result = [i.get() if i.get() is not None else 'Running...'
              for i in tasks_list]
    print result
    return result


def hardview(request):
    if request.method == 'GET':
        content = {'content': get_status_of_tasks()}
        return render(request, 'hardview.html', content)
    elif request.method == 'POST':
        tasks_list.append(hardtask())
        content = {'content': get_status_of_tasks()}
        return render(request, 'hardview.html', content)
