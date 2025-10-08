from google.cloud import firestore
from datetime import datetime, timezone
from typing import Union, List, Generator
from google.cloud.firestore_v1.base_document import DocumentSnapshot


class FirestoreClass:
    FIRESTORE_KEY_FIELD = "firestore_key"
    CREATED_AT_FIELD = "startTime"
    UPDATED_AT_FIELD = "updated_at"

    def __init__(self, database: str, project_id: str):
        self.client = firestore.Client(database=database, project=project_id)

    def _convert_to_dict(
        self, docs: Union[DocumentSnapshot, Generator[DocumentSnapshot, None, None]]
    ) -> Union[dict, List[dict]]:
        if isinstance(docs, Generator):
            return [
                {**doc.to_dict(), **{self.FIRESTORE_KEY_FIELD: doc.id}} for doc in docs
            ]
        elif isinstance(docs, DocumentSnapshot):
            return {**docs.to_dict(), **{self.FIRESTORE_KEY_FIELD: docs.id}}
        else:
            raise TypeError(
                "Expected a DocumentSnapshot or a generator of DocumentSnapshot instances."
            )

    def get_document(self, key: str, collection: str) -> dict:
        document_ref = self.client.collection(collection).document(key)
        return self._convert_to_dict(document_ref.get())

    def get_collection(self, collection: str, limit: int = None) -> List[dict]:
        collection_ref = self.client.collection(collection)
        if limit is not None:
            collection_ref = collection_ref.limit(limit)
        return self._convert_to_dict(collection_ref.stream())

    def get_filtered_collection(
        self, collection: str, filters: dict, limit: int = None
    ) -> List[dict]:
        collection_ref = self.client.collection(collection)

        for field, conditions in filters.items():
            for condition in conditions:
                collection_ref = collection_ref.where(
                    field, condition["operator"], condition["value"]
                )
        if limit is not None:
            collection_ref = collection_ref.limit(limit)

        return self._convert_to_dict(collection_ref.stream())

    def create_document(
        self, collection: str, insert_dict: dict,  document_id: str = None, add_create_date: bool = True
    ) -> str:
        if add_create_date:
            insert_dict[self.CREATED_AT_FIELD] = datetime.now(timezone.utc).isoformat()
        collection_ref = self.client.collection(collection)
        create_time, document_ref = collection_ref.add(insert_dict,document_id)
        return document_ref.id

    def update_document(
        self, collection: str, key: str, update_dict: dict, add_update_date: bool = True
    ) -> dict:
        """
        update_dict = {"status":"Complete"}
        """
        if add_update_date:
            update_dict[self.CREATED_AT_FIELD] = datetime.now(timezone.utc).isoformat()
        document_ref = self.client.collection(collection).document(key)
        document_ref.update(update_dict)
        return self._convert_to_dict(document_ref.get())

    # Functions for testing purposes
    def delete_document(self, collection: str, firestore_id: str) -> None:
        try:
            self.client.collection(collection).document(firestore_id).delete()
            return True

        except Exception as e:
            return False

    def clear_collection_documents(self, collection: str):
        collection_ref = self.client.collection(collection)
        docs = collection_ref.stream()
        for doc in docs:
            doc_dict = doc.to_dict()
            # Delete everything but the reference doc so we can keep the collection
            if doc_dict != {}:
                doc.reference.delete()