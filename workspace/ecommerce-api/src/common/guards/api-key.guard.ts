import {
  Injectable,
  CanActivate,
  ExecutionContext,
  UnauthorizedException,
} from '@nestjs/common';
import { Request } from 'express';

@Injectable()
export class ApiKeyGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<Request>();

    // Use env var or default for tests
    const apiKey = process.env.API_KEY ?? 'secret123';

    // Robust extraction: headers in Node/Express are lower-cased; keep support for variants
    let header: string | string[] | undefined =
      request.headers['x-api-key'] ?? request.headers['X-API-KEY'];

    if (Array.isArray(header)) header = header[0];

    if (!header || header !== apiKey) {
      throw new UnauthorizedException('Missing or invalid API key');
    }

    return true;
  }
}
