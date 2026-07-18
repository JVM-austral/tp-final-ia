export enum OrderStatus {
  PENDING = 'pending',
  SHIPPED = 'shipped',
}

export class Order {
  id: number;
  productId: number;
  quantity: number;
  status: OrderStatus;
  notes?: string;
}
