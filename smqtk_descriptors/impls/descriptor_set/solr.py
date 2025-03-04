import collections
import pickle
import time
from typing import Any, Deque, Dict, Generator, Hashable, Iterable, Mapping, Sequence, Tuple

from smqtk_descriptors import DescriptorElement, DescriptorSet

# Try to import required module
try:
    import solr  # type: ignore
except ImportError:
    solr = None


class SolrDescriptorSet (DescriptorSet):
    """
    Descriptor set that uses a Solr instance as a backend storage medium.

    Fields where components are stored within a document are specified at
    construction time. We optionally set the ``id`` field to a string UUID.
    ``id`` is set because it is a common, required field for unique
    identification of documents.

    Descriptor UUIDs should maintain their uniqueness when converted to a
    string, otherwise this backend will not work well when querying.

    """

    @classmethod
    def is_usable(cls) -> bool:
        return solr is not None

    def __init__(
        self,
        solr_conn_addr: str,
        set_uuid: str,
        set_uuid_field: str,
        d_uid_field: str,
        descriptor_field: str,
        timestamp_field: str,
        solr_params: Dict[str, Any] = None,
        commit_on_add: bool = True,
        max_boolean_clauses: int = 1024,
        pickle_protocol: int = -1
    ):
        """
        Construct a descriptor set pointing to a Solr instance.

        :param solr_conn_addr: HTTP(S) address for the Solr set to use
        :param set_uuid: Unique ID for the descriptor set to use within the
            configured Solr set.
        :param set_uuid_field: Solr set field to store/locate set UUID
            value.
        :param d_uid_field: Solr set field to store/locate descriptor UUID
            values
        :param descriptor_field: Solr set field to store the code-associated
            descriptor object.
        :param timestamp_field: Solr set field to store floating-point UNIX
            timestamps.
        :param solr_params: Dictionary of additional keyword parameters to set
            in the ``solr.Solr`` instance used. See the ``pysolr``
            documentation for available parameters and values.
        :param commit_on_add: Immediately commit changes when one or many
            descriptor are added.
        :param max_boolean_clauses: Solr instance's configured
            maxBooleanClauses configuration property (found in solrconfig.xml
            file). This is needed so we can correctly chunk up batch queries
            without breaking the server. This may also be less than the Solr
            instance's set value.
        :param pickle_protocol: Pickling protocol to use. We will use -1 by
            default (latest version, probably binary).
        """
        super(SolrDescriptorSet, self).__init__()

        self.set_uuid = set_uuid

        self.set_uuid_field = set_uuid_field
        self.d_uid_field = d_uid_field
        self.descriptor_field = descriptor_field
        self.timestamp_field = timestamp_field

        self.commit_on_add = commit_on_add
        self.max_boolean_clauses = int(max_boolean_clauses)
        assert self.max_boolean_clauses >= 2, "Need more clauses"

        self.pickle_protocol = pickle_protocol

        self.solr_params = solr_params
        self.solr = solr.Solr(solr_conn_addr, **solr_params)

    def __getstate__(self) -> Dict[str, Any]:
        return self.get_config()

    def __setstate__(self, state: Mapping[str, Any]) -> None:
        # Shallow copy so we can mutate the top level
        s = dict(state)
        s['solr'] = solr.Solr(s["solr_conn_addr"], **s['solr_params'])
        del s['solr_conn_addr']
        self.__dict__.update(s)

    def _doc_for_code_descr(self, d: DescriptorElement) -> Dict[str, Any]:
        """
        Generate standard identifying document base for the given
        descriptor element.
        """
        uuid = d.uuid()
        return {
            'id': '-'.join([self.set_uuid, str(uuid)]),
            self.set_uuid_field: self.set_uuid,
            self.d_uid_field: uuid,
        }

    def get_config(self) -> Dict[str, Any]:
        return {
            "solr_conn_addr": self.solr.url,
            "set_uuid": self.set_uuid,
            "set_uuid_field": self.set_uuid_field,
            "d_uid_field": self.d_uid_field,
            "descriptor_field": self.descriptor_field,
            "timestamp_field": self.timestamp_field,
            "solr_params": self.solr_params,
            "commit_on_add": self.commit_on_add,
            "max_boolean_clauses": self.max_boolean_clauses,
            "pickle_protocol": self.pickle_protocol,
        }

    def count(self) -> int:
        """
        :return: Number of descriptor elements stored in this set.
        """
        return int(self.solr.
                   select("%s:%s AND %s:*"
                          % (self.set_uuid_field, self.set_uuid,
                             self.descriptor_field))
                   .numFound)

    def clear(self) -> None:
        """
        Clear this descriptor set's entries.
        """
        self.solr.delete_query("%s:%s"
                               % (self.set_uuid_field, self.set_uuid))
        self.solr.commit()

    def has_descriptor(self, uuid: Hashable) -> bool:
        """
        Check if a DescriptorElement with the given UUID exists in this set.

        :param uuid: UUID to query for

        :return: True if a DescriptorElement with the given UUID exists in this
            set, or False if not.
        """
        # Try to select the descriptor
        # TODO: Probably a better way of doing this that's more efficient.
        return bool(
            self.solr.select("%s:%s AND %s:%s"
                             % (self.set_uuid_field, self.set_uuid,
                                self.d_uid_field, uuid)).numFound
        )

    def add_descriptor(self, descriptor: DescriptorElement) -> None:
        """
        Add a descriptor to this set.

        Adding the same descriptor multiple times should not add multiple copies
        of the descriptor in the set (based on UUID). Added descriptors
        overwrite set descriptors based on UUID.

        :param descriptor: Descriptor to add to this set.
        """
        doc = self._doc_for_code_descr(descriptor)
        doc[self.descriptor_field] = pickle.dumps(descriptor,
                                                  self.pickle_protocol)
        doc[self.timestamp_field] = time.time()
        self.solr.add(doc, commit=self.commit_on_add)

    def add_many_descriptors(self, descriptors: Iterable[DescriptorElement]) -> None:
        """
        Add multiple descriptors at one time.

        Adding the same descriptor multiple times should not add multiple copies
        of the descriptor in the set (based on UUID). Added descriptors
        overwrite set descriptors based on UUID.

        :param descriptors: Iterable of descriptor instances to add to this
            set.
        """
        documents = []
        for d in descriptors:
            doc = self._doc_for_code_descr(d)
            doc[self.descriptor_field] = pickle.dumps(d, self.pickle_protocol)
            doc[self.timestamp_field] = time.time()
            documents.append(doc)
        self.solr.add_many(documents)
        if self.commit_on_add:
            self.solr.commit()

    def get_descriptor(self, uuid: Hashable) -> DescriptorElement:
        """
        Get the descriptor in this set that is associated with the given UUID.

        :param uuid: UUID of the DescriptorElement to get.

        :raises KeyError: The given UUID doesn't associate to a
            DescriptorElement in this set.

        :return: DescriptorElement associated with the queried UUID.
        """
        return tuple(self.get_many_descriptors([uuid]))[0]

    def get_many_descriptors(self, uuids: Iterable[Hashable]) -> Generator[DescriptorElement,  None, None]:
        """
        Get an iterator over descriptors associated to given descriptor UUIDs.

        :param uuids: Iterable of descriptor UUIDs to query for.

        :raises KeyError: A given UUID doesn't associate with a
            DescriptorElement in this set.

        :return: Iterator of descriptors associated 1-to-1 to given uuid values.
        """
        # Chunk up query based on max clauses available to us

        def batch_query(_batch: Sequence[Hashable]) -> Generator[DescriptorElement, None, None]:
            """
            :param _batch: Batch of UIDs to select.
            """
            query = ' OR '.join([self.d_uid_field + (':%s' % _uid)
                                 for _uid in _batch])
            r = self.solr.select("%s:%s AND (%s)"
                                 % (self.set_uuid_field, self.set_uuid,
                                    query))
            # result batches come in chunks of 10
            for doc in r.results:
                yield pickle.loads(doc[self.descriptor_field])
            for j in range(r.numFound // 10):
                r = r.next_batch()
                for doc in r.results:
                    yield pickle.loads(doc[self.descriptor_field])

        batch = []
        for uid in uuids:
            batch.append(uid)

            # Will end up using max_clauses-1 OR statements, and one AND
            if len(batch) == self.max_boolean_clauses:
                for d in batch_query(batch):
                    yield d
                batch = []

        # tail batch
        if batch:
            assert len(batch) < self.max_boolean_clauses
            for d in batch_query(batch):
                yield d

    def remove_descriptor(self, uuid: Hashable) -> None:
        """
        Remove a descriptor from this set by the given UUID.

        :param uuid: UUID of the DescriptorElement to remove.

        :raises KeyError: The given UUID doesn't associate to a
            DescriptorElement in this set.
        """
        self.remove_many_descriptors([uuid])

    def remove_many_descriptors(self, uuids: Iterable[Hashable]) -> None:
        """
        Remove descriptors associated to given descriptor UUIDs from this set.

        :param uuids: Iterable of descriptor UUIDs to remove.

        :raises KeyError: A given UUID doesn't associate with a
            DescriptorElement in this set.
        """
        # Chunk up operation based on max clauses available to us

        def batch_op(_batch: Sequence[Hashable]) -> None:
            """
            :param _batch: UIDs to remove from set.
            """
            uuid_query = ' OR '.join([self.d_uid_field + (':%s' % str(_uid))
                                      for _uid in _batch])
            self.solr.delete("%s:%s AND (%s)"
                             % (self.set_uuid_field, self.set_uuid,
                                uuid_query))

        batch: Deque[Hashable] = collections.deque()
        for uid in uuids:
            batch.append(uid)

            # Will end up using max_clauses-1 OR statements, and one AND
            if len(batch) == self.max_boolean_clauses:
                batch_op(batch)
            batch.clear()

        # tail batch
        if batch:
            batch_op(batch)

    def keys(self) -> Generator[Hashable, None, None]:
        """
        Return an iterator over set descriptor keys, which are their UUIDs.
        """
        r = self.solr.select('%s:%s %s:*'
                             % (self.set_uuid_field, self.set_uuid,
                                self.d_uid_field))
        for doc in r.results:
            yield doc[self.d_uid_field]
        for _ in range(r.numFound // 10):
            r = r.next_batch()
            for doc in r.results:
                yield doc[self.d_uid_field]

    def descriptors(self) -> Generator[DescriptorElement, None, None]:
        """
        Return an iterator over set descriptor element instances.
        """
        r = self.solr.select('%s:%s %s:*'
                             % (self.set_uuid_field, self.set_uuid,
                                self.descriptor_field))
        for doc in r.results:
            yield pickle.loads(doc[self.descriptor_field])
        for _ in range(r.numFound // 10):
            r = r.next_batch()
            for doc in r.results:
                yield pickle.loads(doc[self.descriptor_field])

    def items(self) -> Generator[Tuple[Hashable, DescriptorElement], None, None]:
        """
        Return an iterator over set descriptor key and instance pairs.
        """
        r = self.solr.select('%s:%s %s:* %s:*'
                             % (self.set_uuid_field, self.set_uuid,
                                self.d_uid_field, self.descriptor_field))
        for doc in r.results:
            d = pickle.loads(doc[self.descriptor_field])
            yield d.uuid(), d
        for _ in range(r.numFound // 10):
            r = r.next_batch()
            for doc in r.results:
                d = pickle.loads(doc[self.descriptor_field])
                yield d.uuid(), d
