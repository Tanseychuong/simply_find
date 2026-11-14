import { lazy } from "react";
import { Outlet, createBrowserRouter, RouterProvider } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import Layout from "./components/layout/Layout";
import { GuestOnly, RequireAuth, RequireCompany } from "./components/guards";
import Placeholder from "./pages/Placeholder";
import NotFound from "./pages/NotFound";
import Home from "./pages/Home";
import Opportunities from "./pages/Opportunities";
import OpportunityDetail from "./pages/OpportunityDetail";
import CompanyPublic from "./pages/CompanyPublic";

// Loaded when first opened: most visitors only browse roles.
const Login = lazy(() => import("./pages/auth/Login"));
const Register = lazy(() => import("./pages/auth/Register"));
const ForgotPassword = lazy(() => import("./pages/auth/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/auth/ResetPassword"));
const VerifyEmail = lazy(() => import("./pages/auth/VerifyEmail"));
const Claim = lazy(() => import("./pages/auth/Claim"));
const AccountSecurity = lazy(() => import("./pages/account/AccountSecurity"));
const ProfileLayout = lazy(() => import("./pages/profile/ProfileLayout"));
const ProfileOverview = lazy(() => import("./pages/profile/ProfileOverview"));
const AboutStep = lazy(() => import("./pages/profile/ProfileSteps").then((m) => ({ default: m.AboutStep })));
const SkillsStep = lazy(() => import("./pages/profile/ProfileSteps").then((m) => ({ default: m.SkillsStep })));
const StudiesStep = lazy(() => import("./pages/profile/ProfileSteps").then((m) => ({ default: m.StudiesStep })));
const DocumentsStep = lazy(() => import("./pages/profile/DocumentsStep"));
const AccessLog = lazy(() => import("./pages/profile/AccessLog"));
const Apply = lazy(() => import("./pages/Apply"));
const MyApplications = lazy(() => import("./pages/MyApplications"));
const Saved = lazy(() => import("./pages/Saved"));
const PublicDrive = lazy(() => import("./pages/PublicDrive"));
const JoinCompany = lazy(() => import("./pages/company/JoinCompany"));
const InviteAccept = lazy(() => import("./pages/company/InviteAccept"));
const CompanyLayout = lazy(() => import("./pages/company/CompanyLayout"));
const CompanyJobs = lazy(() => import("./pages/company/CompanyJobs"));
const JobForm = lazy(() => import("./pages/company/JobForm"));
const Applicants = lazy(() => import("./pages/company/Applicants"));
const Team = lazy(() => import("./pages/company/Team"));
const CompanyProfile = lazy(() => import("./pages/company/CompanyProfile"));
const Drives = lazy(() => import("./pages/company/Drives"));
const DriveDetail = lazy(() => import("./pages/company/DriveDetail"));

/*
  Route map. Paths marked (fixed) are linked from the backend (emails,
  sitemap, QR codes) and must not change:
  /, /opportunities, /opportunities/:id, /companies/:slug, /companies/join,
  /companies/invite/:token, /company, /applications, /verify-email,
  /reset-password, /claim, /d/:code, /privacy.
*/
const page = (title) => <Placeholder title={title} />;

function Providers() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Outlet />
      </AuthProvider>
    </ThemeProvider>
  );
}

const router = createBrowserRouter([
  {
    element: <Providers />,
    children: [
      {
        element: <Layout />,
        children: [
          // Public
          { path: "/", element: <Home /> },
          { path: "/opportunities", element: <Opportunities /> },
          { path: "/opportunities/:id", element: <OpportunityDetail /> },
          { path: "/companies/join", element: <JoinCompany /> },
          { path: "/companies/invite/:token", element: <InviteAccept /> },
          { path: "/companies/:slug", element: <CompanyPublic /> },
          { path: "/d/:code", element: <PublicDrive /> },
          { path: "/privacy", element: page("Privacy") },

          // Links from emails: work signed in or out
          { path: "/verify-email", element: <VerifyEmail /> },
          { path: "/reset-password", element: <ResetPassword /> },
          { path: "/claim", element: <Claim /> },

          // Signed out only
          {
            element: <GuestOnly />,
            children: [
              { path: "/login", element: <Login /> },
              { path: "/register", element: <Register /> },
              { path: "/forgot-password", element: <ForgotPassword /> },
            ],
          },

          // Signed in
          {
            element: <RequireAuth />,
            children: [
              { path: "/opportunities/:id/apply", element: <Apply /> },
              {
                path: "/profile",
                element: <ProfileLayout />,
                children: [
                  { index: true, element: <ProfileOverview /> },
                  { path: "about", element: <AboutStep /> },
                  { path: "studies", element: <StudiesStep /> },
                  { path: "skills", element: <SkillsStep /> },
                  { path: "documents", element: <DocumentsStep /> },
                  { path: "access", element: <AccessLog /> },
                ],
              },
              { path: "/applications", element: <MyApplications /> },
              { path: "/saved", element: <Saved /> },
              { path: "/account/security", element: <AccountSecurity /> },
              {
                element: <RequireCompany />,
                children: [
                  {
                    path: "/company",
                    element: <CompanyLayout />,
                    children: [
                      { index: true, element: <CompanyJobs /> },
                      { path: "jobs/new", element: <JobForm /> },
                      { path: "jobs/:id/edit", element: <JobForm /> },
                      { path: "jobs/:id/applicants", element: <Applicants /> },
                      { path: "drives", element: <Drives /> },
                      { path: "drives/:id", element: <DriveDetail /> },
                      { path: "team", element: <Team /> },
                      { path: "profile", element: <CompanyProfile /> },
                    ],
                  },
                ],
              },
            ],
          },

          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
