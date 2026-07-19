import { OrdersService } from './orders.service';
import { BadRequestException, NotFoundException } from '@nestjs/common';
import { OrderStatus } from './entities/order.entity';

describe('OrdersService', () => {
  let service: OrdersService;

  beforeEach(() => {
    service = new OrdersService();
  });

  it('should ship a pending order', () => {
    const order = service.create({
      productId: 1,
      quantity: 2,
      status: OrderStatus.PENDING,
    });
    const shipped = service.ship(order.id);
    expect(shipped.status).toBe(OrderStatus.SHIPPED);
    expect(service.findOne(order.id).status).toBe(OrderStatus.SHIPPED);
  });

  it('should throw BadRequestException if already shipped', () => {
    const order = service.create({
      productId: 1,
      quantity: 2,
      status: OrderStatus.PENDING,
    });
    service.ship(order.id);
    try {
      service.ship(order.id);
      // If no error thrown, fail the test
      fail('Expected BadRequestException');
    } catch (e) {
      expect(e).toBeInstanceOf(BadRequestException);
      expect(e.message).toBe(`Order #${order.id} is already shipped`);
    }
  });

  it('should throw NotFoundException for non-existent order', () => {
    try {
      service.ship(999);
      fail('Expected NotFoundException');
    } catch (e) {
      expect(e).toBeInstanceOf(NotFoundException);
      expect(e.message).toBe('Order #999 not found');
    }
  });
});
