# Task 005: Original Django 4.2 failure tracebacks

Captured with the default executable (`Python 3.14.7`, `Django 4.2.27`). Each section contains the complete primary traceback through its original exception. Django 4.2's test exception reporter then tried to render a debug page and emitted a secondary copy of the same `Context` copying failure. Under the project environment (`Python 3.14.7`, `Django 6.1.2`) the complete suite passes, so that secondary logging failure is not present in the accepted run.

## ERROR: test_clip_planner_page_renders_200 (apps.calculators.tests.test_clip_planning.ClipPlannerWebEndpointTests.test_clip_planner_page_renders_200)

```text
Traceback (most recent call last):
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\core\handlers\exception.py", line 55, in inner
    response = get_response(request)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\core\handlers\base.py", line 197, in _get_response
    response = wrapped_callback(request, *callback_args, **callback_kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\views\generic\base.py", line 105, in view
    return self.dispatch(request, *args, **kwargs)
           ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\utils\decorators.py", line 46, in _wrapper
    return bound_method(*args, **kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\utils\decorators.py", line 134, in _wrapper_view
    response = view_func(request, *args, **kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\views\generic\base.py", line 144, in dispatch
    return handler(request, *args, **kwargs)
  File "C:\Users\Admin\Desktop\Dev\video_calculator\apps\calculators\views.py", line 133, in get
    return render(request, 'calculators/clip_planner_test.html', context)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\shortcuts.py", line 24, in render
    content = loader.render_to_string(template_name, context, request, using=using)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\loader.py", line 62, in render_to_string
    return template.render(context, request)
           ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\backends\django.py", line 61, in render
    return self.template.render(context)
           ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\base.py", line 175, in render
    return self._render(context)
           ~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\test\utils.py", line 111, in instrumented_test_render
    template_rendered.send(sender=self, template=self, context=context)
    ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\dispatch\dispatcher.py", line 177, in send
    (receiver, receiver(signal=self, sender=sender, **named))
               ~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\test\client.py", line 267, in store_rendered_templates
    store["context"].append(copy(context))
                            ~~~~^^^^^^^^^
  File "C:\Python314\Lib\copy.py", line 82, in copy
    return copier(x)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\context.py", line 158, in __copy__
    duplicate = super().__copy__()
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\context.py", line 39, in __copy__
    duplicate.dicts = self.dicts[:]
    ^^^^^^^^^^^^^^^
AttributeError: 'super' object has no attribute 'dicts' and no __dict__ for setting new attributes
```

## ERROR: test_existing_narration_page_and_index_still_functional (apps.calculators.tests.test_clip_planning.ClipPlannerWebEndpointTests.test_existing_narration_page_and_index_still_functional)

```text
Traceback (most recent call last):
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\core\handlers\exception.py", line 55, in inner
    response = get_response(request)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\core\handlers\base.py", line 197, in _get_response
    response = wrapped_callback(request, *callback_args, **callback_kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\views\generic\base.py", line 105, in view
    return self.dispatch(request, *args, **kwargs)
           ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\utils\decorators.py", line 46, in _wrapper
    return bound_method(*args, **kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\utils\decorators.py", line 134, in _wrapper_view
    response = view_func(request, *args, **kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\views\generic\base.py", line 144, in dispatch
    return handler(request, *args, **kwargs)
  File "C:\Users\Admin\Desktop\Dev\video_calculator\apps\calculators\views.py", line 42, in get
    return render(request, 'calculators/narration_test.html', context)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\shortcuts.py", line 24, in render
    content = loader.render_to_string(template_name, context, request, using=using)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\loader.py", line 62, in render_to_string
    return template.render(context, request)
           ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\backends\django.py", line 61, in render
    return self.template.render(context)
           ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\base.py", line 175, in render
    return self._render(context)
           ~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\test\utils.py", line 111, in instrumented_test_render
    template_rendered.send(sender=self, template=self, context=context)
    ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\dispatch\dispatcher.py", line 177, in send
    (receiver, receiver(signal=self, sender=sender, **named))
               ~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\test\client.py", line 267, in store_rendered_templates
    store["context"].append(copy(context))
                            ~~~~^^^^^^^^^
  File "C:\Python314\Lib\copy.py", line 82, in copy
    return copier(x)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\context.py", line 158, in __copy__
    duplicate = super().__copy__()
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\context.py", line 39, in __copy__
    duplicate.dicts = self.dicts[:]
    ^^^^^^^^^^^^^^^
AttributeError: 'super' object has no attribute 'dicts' and no __dict__ for setting new attributes
```

## ERROR: test_interactive_page_loads (apps.calculators.tests.test_narration.NarrationWebEndpointTests.test_interactive_page_loads)

```text
Traceback (most recent call last):
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\core\handlers\exception.py", line 55, in inner
    response = get_response(request)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\core\handlers\base.py", line 197, in _get_response
    response = wrapped_callback(request, *callback_args, **callback_kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\views\generic\base.py", line 105, in view
    return self.dispatch(request, *args, **kwargs)
           ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\utils\decorators.py", line 46, in _wrapper
    return bound_method(*args, **kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\utils\decorators.py", line 134, in _wrapper_view
    response = view_func(request, *args, **kwargs)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\views\generic\base.py", line 144, in dispatch
    return handler(request, *args, **kwargs)
  File "C:\Users\Admin\Desktop\Dev\video_calculator\apps\calculators\views.py", line 42, in get
    return render(request, 'calculators/narration_test.html', context)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\shortcuts.py", line 24, in render
    content = loader.render_to_string(template_name, context, request, using=using)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\loader.py", line 62, in render_to_string
    return template.render(context, request)
           ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\backends\django.py", line 61, in render
    return self.template.render(context)
           ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\base.py", line 175, in render
    return self._render(context)
           ~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\test\utils.py", line 111, in instrumented_test_render
    template_rendered.send(sender=self, template=self, context=context)
    ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\dispatch\dispatcher.py", line 177, in send
    (receiver, receiver(signal=self, sender=sender, **named))
               ~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\test\client.py", line 267, in store_rendered_templates
    store["context"].append(copy(context))
                            ~~~~^^^^^^^^^
  File "C:\Python314\Lib\copy.py", line 82, in copy
    return copier(x)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\context.py", line 158, in __copy__
    duplicate = super().__copy__()
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\context.py", line 39, in __copy__
    duplicate.dicts = self.dicts[:]
    ^^^^^^^^^^^^^^^
AttributeError: 'super' object has no attribute 'dicts' and no __dict__ for setting new attributes
```

## ERROR: test_home_page_renders_successfully (videocalculatorproject.tests.test_project_setup.HomeViewTests.test_home_page_renders_successfully)

```text
Traceback (most recent call last):
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\core\handlers\exception.py", line 55, in inner
    response = get_response(request)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\core\handlers\base.py", line 220, in _get_response
    response = response.render()
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\response.py", line 114, in render
    self.content = self.rendered_content
                   ^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\response.py", line 92, in rendered_content
    return template.render(context, self._request)
           ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\backends\django.py", line 61, in render
    return self.template.render(context)
           ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\base.py", line 175, in render
    return self._render(context)
           ~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\test\utils.py", line 111, in instrumented_test_render
    template_rendered.send(sender=self, template=self, context=context)
    ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\dispatch\dispatcher.py", line 177, in send
    (receiver, receiver(signal=self, sender=sender, **named))
               ~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\test\client.py", line 267, in store_rendered_templates
    store["context"].append(copy(context))
                            ~~~~^^^^^^^^^
  File "C:\Python314\Lib\copy.py", line 82, in copy
    return copier(x)
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\context.py", line 158, in __copy__
    duplicate = super().__copy__()
  File "C:\Users\Admin\AppData\Roaming\Python\Python314\site-packages\django\template\context.py", line 39, in __copy__
    duplicate.dicts = self.dicts[:]
    ^^^^^^^^^^^^^^^
AttributeError: 'super' object has no attribute 'dicts' and no __dict__ for setting new attributes
```
