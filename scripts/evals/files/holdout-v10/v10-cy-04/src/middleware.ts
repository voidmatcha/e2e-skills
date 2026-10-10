import { NextResponse, type NextRequest } from 'next/server';

const PROTECTED = ['/rota', '/rota/nights'];

export function middleware(request: NextRequest) {
  const signedIn = request.cookies.has('ward_session');
  if (!signedIn && PROTECTED.some((path) => request.nextUrl.pathname.startsWith(path))) {
    const target = new URL('/sign-in', request.url);
    target.searchParams.set('returnTo', request.nextUrl.pathname);
    return NextResponse.redirect(target);
  }
  return NextResponse.next();
}
