"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.moveUserToMatchingOrg = moveUserToMatchingOrg;
exports.handler = handler;
exports.cleanUpVerificationTokens = cleanUpVerificationTokens;
const dayjs_1 = __importDefault(require("@calcom/dayjs"));
const onboarding_path_service_1 = require("@calcom/features/onboarding/lib/onboarding-path.service");
const constants_1 = require("@calcom/lib/constants");
const prisma_1 = require("@calcom/prisma");
const zod_utils_1 = require("@calcom/prisma/zod-utils");
const zod_1 = require("zod");
const verifySchema = zod_1.z.object({
    token: zod_1.z.string(),
});
const USER_ALREADY_EXISTING_MESSAGE = "A User already exists with this email";
// TODO: To be unit tested
async function moveUserToMatchingOrg({ email }) {
    const organizationRepository = { findUniqueNonPlatformOrgsByMatchingAutoAcceptEmail: async (_args) => null };
    const org = await organizationRepository.findUniqueNonPlatformOrgsByMatchingAutoAcceptEmail({ email });
    if (!org) {
        return;
    }
    ({});
}
async function handler(req, res) {
    const { token } = verifySchema.parse(req.query);
    const foundToken = await prisma_1.prisma.verificationToken.findFirst({
        where: {
            token,
        },
    });
    if (!foundToken) {
        return res.status(401).json({ message: "No token found" });
    }
    if ((0, dayjs_1.default)(foundToken?.expires).isBefore((0, dayjs_1.default)())) {
        return res.status(401).json({ message: "Token expired" });
    }
    // The user is verifying the secondary email
    if (foundToken?.secondaryEmailId) {
        await prisma_1.prisma.secondaryEmail.update({
            where: {
                id: foundToken.secondaryEmailId,
                email: foundToken?.identifier,
            },
            data: {
                emailVerified: new Date(),
            },
        });
        await cleanUpVerificationTokens(foundToken.id);
        return res.redirect(`${constants_1.WEBAPP_URL}/settings/my-account/profile`);
    }
    const user = await prisma_1.prisma.user.findFirst({
        where: {
            email: foundToken?.identifier,
        },
    });
    if (!user) {
        return res.status(401).json({ message: "Cannot find a user attached to this token" });
    }
    const userMetadataParsed = zod_utils_1.userMetadata.parse(user.metadata);
    // Attach the new email and verify
    if (userMetadataParsed?.emailChangeWaitingForVerification) {
        // Ensure this email isn't in use
        const existingUser = await prisma_1.prisma.user.findUnique({
            where: { email: userMetadataParsed?.emailChangeWaitingForVerification },
            select: {
                id: true,
            },
        });
        if (existingUser) {
            return res.status(401).json({ message: USER_ALREADY_EXISTING_MESSAGE });
        }
        // Ensure this email isn't being added by another user as secondary email
        const existingSecondaryUser = await prisma_1.prisma.secondaryEmail.findUnique({
            where: {
                email: userMetadataParsed?.emailChangeWaitingForVerification,
            },
            select: {
                id: true,
                userId: true,
            },
        });
        if (existingSecondaryUser && existingSecondaryUser.userId !== user.id) {
            return res.status(401).json({ message: USER_ALREADY_EXISTING_MESSAGE });
        }
        const oldEmail = user.email;
        const updatedEmail = userMetadataParsed.emailChangeWaitingForVerification;
        delete userMetadataParsed.emailChangeWaitingForVerification;
        // Update and re-verify
        await prisma_1.prisma.user.update({
            where: {
                id: user.id,
            },
            data: {
                email: updatedEmail,
                metadata: userMetadataParsed,
            },
        });
        if (constants_1.IS_STRIPE_ENABLED && userMetadataParsed.stripeCustomerId) {
            const billingService = { updateCustomer: async (_args) => { } };
            await billingService.updateCustomer({
                customerId: userMetadataParsed.stripeCustomerId,
                email: updatedEmail,
            });
        }
        // The user is trying to update the email to an already existing unverified secondary email of his
        // so we swap the emails and its verified status
        if (existingSecondaryUser?.userId === user.id) {
            await prisma_1.prisma.secondaryEmail.update({
                where: {
                    id: existingSecondaryUser.id,
                    userId: user.id,
                },
                data: {
                    email: oldEmail,
                    emailVerified: user.emailVerified,
                },
            });
        }
        await cleanUpVerificationTokens(foundToken.id);
        return res.status(200).json({
            updatedEmail,
        });
    }
    await prisma_1.prisma.user.update({
        where: {
            id: user.id,
        },
        data: {
            emailVerified: new Date(),
        },
    });
    const hasCompletedOnboarding = user.completedOnboarding;
    await moveUserToMatchingOrg({ email: user.email });
    const gettingStartedPath = await onboarding_path_service_1.OnboardingPathService.getGettingStartedPath();
    return res.redirect(`${constants_1.WEBAPP_URL}${hasCompletedOnboarding ? "/event-types" : gettingStartedPath}`);
}
async function cleanUpVerificationTokens(id) {
    // Delete token from DB after it has been used
    await prisma_1.prisma.verificationToken.delete({
        where: {
            id,
        },
    });
}
