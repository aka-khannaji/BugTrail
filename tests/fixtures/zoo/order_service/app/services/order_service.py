import time


def db_transaction():
    return DatabaseTransaction()


class DatabaseTransaction:
    def __init__(self):
        self.committed = False

    def execute(self, query, params):
        pass

    def commit(self):
        self.committed = True


class OrderService:
    def create_order(self, order_id: int) -> dict:
        tx = db_transaction()
        tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))
        for attempt in range(3):
            if tx.committed:
                break
            tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))  # retry
        tx.commit()
        return {"id": order_id}