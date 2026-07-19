import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from './../src/app.module';
import { Express } from 'express';

const API_KEY = process.env.API_KEY ?? 'secret123';

// Test helper types to avoid unsafe `any` in e2e specs
type TestOrder = {
  id: number;
  productId: number;
  quantity: number;
  status: string;
  notes?: string;
};

type ErrorBody = {
  message: string;
};

describe('Orders (e2e)', () => {
  let app: INestApplication;

  beforeEach(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({ whitelist: true, transform: true }),
    );
    await app.init();
  });

  it('ships a pending order successfully', async () => {
    const server = app.getHttpServer() as unknown as Express;

    // create an order (defaults to pending if status is provided as PENDING)
    const createRes = await request(server)
      .post('/orders')
      .set('x-api-key', API_KEY)
      .send({ productId: 1, quantity: 2, status: 'pending' })
      .expect(201);

    const order = createRes.body as TestOrder;

    const shipRes = await request(server)
      .patch(`/orders/${order.id}/ship`)
      .set('x-api-key', API_KEY)
      .expect(200);

    const shipBody = shipRes.body as { status: string };
    expect(shipBody.status).toBe('shipped');
  });

  it('returns 400 if order already shipped', async () => {
    const server = app.getHttpServer() as unknown as Express;

    const createRes = await request(server)
      .post('/orders')
      .set('x-api-key', API_KEY)
      .send({ productId: 2, quantity: 1, status: 'pending' })
      .expect(201);

    const order = createRes.body as TestOrder;

    await request(server)
      .patch(`/orders/${order.id}/ship`)
      .set('x-api-key', API_KEY)
      .expect(200);

    const errorRes = await request(server)
      .patch(`/orders/${order.id}/ship`)
      .set('x-api-key', API_KEY)
      .expect(400);

    const errorBody = errorRes.body as ErrorBody;
    expect(errorBody.message).toBe(`Order #${order.id} is already shipped`);
  });

  it('returns 404 if order not found', async () => {
    const server = app.getHttpServer() as unknown as Express;

    const res = await request(server)
      .patch('/orders/999/ship')
      .set('x-api-key', API_KEY)
      .expect(404);

    const errBody = res.body as ErrorBody;
    expect(errBody.message).toBe('Order #999 not found');
  });
});
