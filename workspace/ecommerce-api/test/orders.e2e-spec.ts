import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from './../src/app.module';

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
    // create an order (defaults to pending if status is provided as PENDING)
    const createRes = await request(app.getHttpServer())
      .post('/orders')
      .send({ productId: 1, quantity: 2, status: 'pending' })
      .expect(201);

    const order = createRes.body;

    const shipRes = await request(app.getHttpServer())
      .patch(`/orders/${order.id}/ship`)
      .expect(200);

    expect(shipRes.body.status).toBe('shipped');
  });

  it('returns 400 if order already shipped', async () => {
    const createRes = await request(app.getHttpServer())
      .post('/orders')
      .send({ productId: 2, quantity: 1, status: 'pending' })
      .expect(201);

    const order = createRes.body;

    await request(app.getHttpServer())
      .patch(`/orders/${order.id}/ship`)
      .expect(200);

    const errorRes = await request(app.getHttpServer())
      .patch(`/orders/${order.id}/ship`)
      .expect(400);

    expect(errorRes.body.message).toBe(`Order #${order.id} is already shipped`);
  });

  it('returns 404 if order not found', async () => {
    const res = await request(app.getHttpServer())
      .patch('/orders/999/ship')
      .expect(404);

    expect(res.body.message).toBe('Order #999 not found');
  });
});
