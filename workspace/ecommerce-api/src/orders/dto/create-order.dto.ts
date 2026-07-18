import {
  IsInt,
  Min,
  IsEnum,
  IsOptional,
  IsString,
  MaxLength,
} from 'class-validator';
import { OrderStatus } from '../entities/order.entity';

export class CreateOrderDto {
  @IsInt()
  @Min(1)
  productId: number;

  @IsInt()
  @Min(1)
  quantity: number;

  @IsEnum(OrderStatus)
  status: OrderStatus;

  @IsString()
  @IsOptional()
  @MaxLength(500)
  notes?: string;
}
