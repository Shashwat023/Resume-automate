import { z } from 'zod';

export const educationSchema = z.object({
  id: z.string().optional(),
  degree: z.string().min(1, 'Degree is required'),
  university: z.string().min(1, 'University is required'),
  fieldOfStudy: z.string().min(1, 'Field of study is required'),
  startDate: z.string().min(1, 'Start date is required'),
  endDate: z.string().optional(),
  grade: z.string().optional(),
  description: z.string().optional(),
});

export const experienceSchema = z.object({
  id: z.string().optional(),
  company: z.string().min(1, 'Company is required'),
  role: z.string().min(1, 'Role is required'),
  location: z.string().optional(),
  startDate: z.string().min(1, 'Start date is required'),
  endDate: z.string().optional(),
  currentlyWorking: z.boolean().default(false),
  description: z.string().optional(),
  achievements: z.string().optional(),
});

export const profileSchema = z.object({
  // 1. Personal Information
  personal: z.object({
    firstName: z.string().min(1, 'First name is required'),
    middleName: z.string().optional(),
    lastName: z.string().min(1, 'Last name is required'),
    gender: z.string().optional(),
    dateOfBirth: z.string().optional(),
    nationality: z.string().optional(),
  }),

  // 2. Contact Information
  contact: z.object({
    email: z.string().email('Invalid email format').min(1, 'Email is required'),
    phone: z.string().min(1, 'Phone number is required'),
    alternatePhone: z.string().optional(),
    country: z.string().optional(),
    state: z.string().optional(),
    city: z.string().optional(),
    postalCode: z.string().optional(),
    fullAddress: z.string().optional(),
    timezone: z.string().optional(),
  }),

  // 3. Professional Information
  professional: z.object({
    currentJobTitle: z.string().optional(),
    currentCompany: z.string().optional(),
    // valueAsNumber turns an empty number input into NaN (not undefined),
    // which z.number().optional() rejects — preprocess NaN back to undefined
    // so leaving these fields blank doesn't silently block autosave forever.
    yearsOfExperience: z.preprocess(
      (v) => (typeof v === 'number' && Number.isNaN(v) ? undefined : v),
      z.number().min(0).optional()
    ),
    totalExperience: z.preprocess(
      (v) => (typeof v === 'number' && Number.isNaN(v) ? undefined : v),
      z.number().min(0).optional()
    ),
    industry: z.string().optional(),
    employmentStatus: z.string().optional(),
    noticePeriod: z.string().optional(),
  }),

  // 4. Education (Array)
  education: z.array(educationSchema).default([]),

  // 5. Employment (Array)
  employment: z.array(experienceSchema).default([]),

  // 6. Social Links
  social: z.object({
    linkedin: z.string().url('Must be a valid URL').optional().or(z.literal('')),
    github: z.string().url('Must be a valid URL').optional().or(z.literal('')),
    portfolio: z.string().url('Must be a valid URL').optional().or(z.literal('')),
    twitter: z.string().url('Must be a valid URL').optional().or(z.literal('')),
    kaggle: z.string().url('Must be a valid URL').optional().or(z.literal('')),
    huggingFace: z.string().url('Must be a valid URL').optional().or(z.literal('')),
    stackOverflow: z.string().url('Must be a valid URL').optional().or(z.literal('')),
  }),

  // 7. Work Authorization
  workAuthorization: z.object({
    currentCountry: z.string().optional(),
    visaStatus: z.string().optional(),
    workAuthorization: z.string().optional(),
    sponsorshipRequired: z.boolean().default(false),
    eligibleCountries: z.array(z.string()).default([]),
    willingToRelocate: z.boolean().default(false),
    remoteOnly: z.boolean().default(false),
  }),

  // 8. Salary Preferences
  salary: z.object({
    currentSalary: z.string().optional(),
    expectedSalary: z.string().optional(),
    currency: z.string().default('USD'),
    employmentType: z.string().optional(), // Full-time, Contract, etc.
    preferredJobType: z.string().optional(),
  }),

  // 9. Job Preferences
  preferences: z.object({
    preferredLocations: z.array(z.string()).default([]),
    preferredRoles: z.array(z.string()).default([]),
    preferredIndustries: z.array(z.string()).default([]),
    preferredAts: z.array(z.string()).default([]),
    remote: z.boolean().default(false),
    hybrid: z.boolean().default(false),
    onsite: z.boolean().default(false),
    travelPercentage: z.string().optional(),
  }),

  // 10. Skills
  skills: z.array(z.string()).default([]),

  // 11. Summary
  summary: z.string().max(2000, 'Summary is too long').optional(),

  // 12. Additional Information
  additional: z.object({
    veteranStatus: z.string().optional(),
    disabilityStatus: z.string().optional(),
    genderIdentity: z.string().optional(),
    pronouns: z.string().optional(),
    raceEthnicity: z.string().optional(),
  }),
});

export type ProfileFormValues = z.infer<typeof profileSchema>;
