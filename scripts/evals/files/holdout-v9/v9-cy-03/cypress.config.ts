import { defineConfig } from 'cypress';

export default defineConfig({
  e2e: {
    baseUrl: 'http://localhost:3000',
    // Cognito sign-in is opt-in. Set cognitoUsername/cognitoPassword only for the
    // dedicated "e2e-test" user pool, which is reset nightly and holds no customer data.
    env: { cognitoUsername: '', cognitoPassword: '' },
  },
});
