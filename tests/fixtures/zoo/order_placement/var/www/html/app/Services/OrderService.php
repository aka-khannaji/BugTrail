<?php

namespace App\Services;

use App\Models\Order;

class OrderService
{
    public function createOrder(int $orderId): array
    {
        $order = Order::create(['id' => $orderId]);
        return ['id' => $order->id];
    }
}
