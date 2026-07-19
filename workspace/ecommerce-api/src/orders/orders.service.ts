import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { Order, OrderStatus } from './entities/order.entity';
import { CreateOrderDto } from './dto/create-order.dto';
import { UpdateOrderDto } from './dto/update-order.dto';

@Injectable()
export class OrdersService {
  private orders: Order[] = [];
  private nextId = 1;

  create(createOrderDto: CreateOrderDto): Order {
    const order: Order = { id: this.nextId++, ...createOrderDto };
    this.orders.push(order);
    return order;
  }

  findAll(): Order[] {
    return this.orders;
  }

  findOne(id: number): Order {
    const order = this.orders.find((o) => o.id === id);
    if (!order) throw new NotFoundException(`Order #${id} not found`);
    return order;
  }

  findByStatus(status: OrderStatus): Order[] {
    return this.orders.filter((o) => o.status === status);
  }

  update(id: number, updateOrderDto: UpdateOrderDto): Order {
    const order = this.findOne(id);
    Object.assign(order, updateOrderDto);
    return order;
  }

  ship(id: number): Order {
    const order = this.findOne(id);
    if (order.status === OrderStatus.SHIPPED) {
      throw new BadRequestException(`Order #${id} is already shipped`);
    }
    order.status = OrderStatus.SHIPPED;
    return order;
  }

  remove(id: number): void {
    this.findOne(id);
    this.orders = this.orders.filter((o) => o.id !== id);
  }
}
