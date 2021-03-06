import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import OneToOneField
from django.db.transaction import atomic
from django.utils import six

try:
    from django.db.models.fields.related import SingleRelatedObjectDescriptor
except ImportError:
    from django.db.models.fields.related_descriptors import ReverseOneToOneDescriptor as SingleRelatedObjectDescriptor


class AutoSingleRelatedObjectDescriptor(SingleRelatedObjectDescriptor):
    """
    The descriptor that handles the object creation for an AutoOneToOneField.
    """
    @atomic
    def __get__(self, instance, instance_type=None):
        model = getattr(self.related, 'related_model', self.related.model)

        try:
            return (super(AutoSingleRelatedObjectDescriptor, self)
                    .__get__(instance, instance_type))
        except model.DoesNotExist:
            # Using get_or_create instead() of save() or create() as it better handles race conditions
            model.objects.get_or_create(**{self.related.field.name: instance})

            # Don't return obj directly, otherwise it won't be added
            # to Django's cache, and the first 2 calls to obj.relobj
            # will return 2 different in-memory objects
            return (super(AutoSingleRelatedObjectDescriptor, self)
                    .__get__(instance, instance_type))


class AutoOneToOneField(OneToOneField):
    '''
    OneToOneField creates related object on first call if it doesnt exist yet.
    Use it instead of original OneToOne field.

    example:

        class MyProfile(models.Model):
            user = AutoOneToOneField(User, primary_key=True)
            home_page = models.URLField(max_length=255, blank=True)
            icq = models.IntegerField(max_length=255, null=True)
    '''
    def contribute_to_related_class(self, cls, related):
        setattr(cls, related.get_accessor_name(), AutoSingleRelatedObjectDescriptor(related))


class JSONField(models.TextField):
    """
    JSONField is a generic textfield that neatly serializes/unserializes
    JSON objects seamlessly.
    Django snippet #1478

    Custom serializer/deserializer functions can be used to customize field's behavior.
    Defaults:
     - serializer: json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, indent=2, separators=(',', ': '))
     - deserializer: json.loads(value)

    example:
        class Page(models.Model):
            data = JSONField(blank=True, null=True)


        page = Page.objects.get(pk=5)
        page.data = {'title': 'test', 'type': 3}
        page.save()
    """

    def __init__(self, *args, **kwargs):
        def dumps(value):
            return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, indent=2, separators=(',', ': '))

        self.serializer = kwargs.pop('serializer', dumps)
        self.deserializer = kwargs.pop('deserializer', json.loads)

        super(JSONField, self).__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super(JSONField, self).deconstruct()
        kwargs['serializer'] = self.serializer
        kwargs['deserializer'] = self.deserializer
        return name, path, args, kwargs

    def to_python(self, value):
        """
        Convert a string from the database to a Python value.
        """
        if value == "":
            return None

        try:
            if isinstance(value, six.string_types):
                return self.deserializer(value)
            elif isinstance(value, bytes):
                return self.deserializer(value.decode('utf8'))
        except ValueError:
            pass
        return value

    def get_prep_value(self, value):
        """
        Convert the value to a string so it can be stored in the database.
        """
        if value == "":
            return None
        if isinstance(value, dict) or isinstance(value, list):
            return self.serializer(value)
        return super(JSONField, self).get_prep_value(value)

    def from_db_value(self, value, *args, **kwargs):
        return self.to_python(value)

    def get_default(self):
        # Override Django's `get_default()` to avoid stringification.
        if self.has_default():
            if callable(self.default):
                return self.default()
            return self.default
        return ""

    def get_db_prep_save(self, value, *args, **kwargs):
        if value == "":
            return None
        if isinstance(value, dict) or isinstance(value, list):
            return self.serializer(value)
        else:
            return super(JSONField, self).get_db_prep_save(value, *args, **kwargs)

    def value_from_object(self, obj):
        value = super(JSONField, self).value_from_object(obj)
        if self.null and value is None:
            return None
        return self.serializer(value)
