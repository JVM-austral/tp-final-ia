import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { ProductsService } from './products.service';

describe('ProductsService', () => {
  let service: ProductsService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [ProductsService],
    }).compile();

    service = module.get<ProductsService>(ProductsService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('creates a product and assigns an incremental id', () => {
    const product = service.create({ name: 'Mouse', price: 10, stock: 5 });
    expect(product.id).toBe(1);
    expect(service.findAll()).toHaveLength(1);
  });

  it('finds a product by id', () => {
    const created = service.create({ name: 'Keyboard', price: 20, stock: 3 });
    expect(service.findOne(created.id)).toEqual(created);
  });

  it('throws NotFoundException when the product does not exist', () => {
    expect(() => service.findOne(999)).toThrow(NotFoundException);
  });

  it('updates a product', () => {
    const created = service.create({ name: 'Monitor', price: 100, stock: 2 });
    const updated = service.update(created.id, { stock: 1 });
    expect(updated.stock).toBe(1);
  });

  it('removes a product', () => {
    const created = service.create({ name: 'Webcam', price: 30, stock: 4 });
    service.remove(created.id);
    expect(() => service.findOne(created.id)).toThrow(NotFoundException);
  });
});
