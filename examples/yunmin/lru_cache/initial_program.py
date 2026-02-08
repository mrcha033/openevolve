# EVOLVE-BLOCK-START

class LRUCache:
    """
    Simple LRU cache for integer keys.
    access(key) returns True on hit, False on miss.
    """

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.order = []
        self.set = set()

    def access(self, key: int) -> bool:
        if key in self.set:
            # Move to front
            idx = self.order.index(key)
            self.order.pop(idx)
            self.order.append(key)
            return True

        # Miss
        if len(self.order) >= self.capacity:
            evict = self.order.pop(0)
            self.set.remove(evict)
        self.order.append(key)
        self.set.add(key)
        return False

# EVOLVE-BLOCK-END
