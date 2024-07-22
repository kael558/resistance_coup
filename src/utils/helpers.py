def cosine_similarity(a, b):
    dot_product = sum([a[i] * b[i] for i in range(len(a))])

    magnitude_a = sum([a[i] ** 2 for i in range(len(a))]) ** 0.5

    magnitude_b = sum([b[i] ** 2 for i in range(len(b))]) ** 0.5

    return dot_product / (magnitude_a * magnitude_b)


def min_max_normalize(data):
    if not data:
        return []

    min_value = min(data)
    max_value = max(data)

    if min_value == max_value:
        return [0.5] * len(data)
    else:
        return [(value - min_value) / (max_value - min_value) for value in data]
