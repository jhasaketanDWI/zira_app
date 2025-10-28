// src/router/AppRouter.jsx

import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HomePage from "../pages/HomePage.jsx";
import GenericPage from "../pages/GenericPage.jsx";
import LoginPage from "../pages/Login.jsx";
import SignupPage from "../pages/Signup.jsx";
import DashboardLayout from "../layout/DashboardLayout.jsx";
import AboutPage from "../pages/AboutUs.jsx";
import Services from "../pages/Services.jsx";
import Projects from "../pages/Projects.jsx";
import BacklogPage from "../components/Dashboardpages/BacklogPage.jsx";
import PageContent from "../components/Dashboardpages/PageContent.jsx";
import Summary from "../components/Dashboardpages/Summary.jsx";
import List from "../components/Dashboardpages/List.jsx";

import Statisticspage from "../pages/sidenav_pages/Statisticspage.jsx";
import Documents from "../pages/sidenav_pages/Documents.jsx";
import Notifications from "../pages/sidenav_pages/Notification.jsx";
import Wallet from "../pages/sidenav_pages/Wallet.jsx";
import Settings from "../pages/sidenav_pages/Settings.jsx";
import Board from "../components/Dashboardpages/Board.jsx";
import Calendar from "../components/Dashboardpages/Calendar.jsx";
import Timeline from "../components/Dashboardpages/Timeline.jsx";

import Projectmanager from "../components/Dashboardpages/Project management/Teammanagement.jsx";
import Pmprojectmanager from "../components/Dashboardpages/projectmanager/Project managementmg/PmTeammanagement.jsx"


import DeveloperProjects from "../pages/developerPages/DeveloperProjects.jsx";
import DeveloperBacklogPage from "../components/developerDashboardpages/DeveloperBacklog.jsx";
import DevelopersBoard from "../components/developerDashboardpages/DeveloperBoard.jsx";
import DevelopersCalendar from "../components/developerDashboardpages/DeveloperCalendar.jsx";
import DevelopersTimeline from "../components/developerDashboardpages/DeveloperTimeline.jsx";
import DevelopersSummary from "../components/developerDashboardpages/DeveloperSummary.jsx";
import DevelopersList from "../components/developerDashboardpages/DeveloperList.jsx";
import DevelopersPageContent from "../components/developerDashboardpages/DeveloperPageContent.jsx";
import Developerprojectmanager from "../components/developerDashboardpages/Project management developer/DevTeammanagement.jsx";
import DevEditUserModal from "../components/developerDashboardpages/Project management developer/DevEditUserModal.jsx";
//import DeveloperDashboardLayout from "../layout/DeveloperDashboardLayout.jsx";

import DevDocuments from "../pages/developerPages/sidenav_pages/DevDocuments.jsx";
import DevNotification from "../pages/developerPages/sidenav_pages/DevNotification.jsx";
import DevSettings from "../pages/developerPages/sidenav_pages/DevSettings.jsx";


import TesterProjects from "../pages/testerPages/TesterProjects.jsx";

import PmProjects from "../pages/projectmanagerpages/PmProjects.jsx";
import SetPasswordPage from "../components/Dashboardpages/Project management/Setpassword.jsx";
import Pmdashboardlayout from "../layout/Pmdasboardlayout.jsx";
import PmBacklogPage from "../components/Dashboardpages/projectmanager/pmpages/Pmbacklogpage.jsx";


import PmDocuments from "../pages/projectmanagerpages/sidenav_pages/Documents.jsx";
import PmNotifications from "../pages/projectmanagerpages/sidenav_pages/Notification.jsx";
import PmSettings from "../pages/projectmanagerpages/sidenav_pages/Settings.jsx";
import PmSummary from "../components/Dashboardpages/projectmanager/pmpages/Pmsummary.jsx";
import PmList from "../components/Dashboardpages/projectmanager/pmpages/Pmlist.jsx";
import PmBoard from "../components/Dashboardpages/projectmanager/pmpages/Pmboard.jsx";
import PmTimeline from "../components/Dashboardpages/projectmanager/pmpages/Pmtimeline.jsx";
import PmCalendar from "../components/Dashboardpages/projectmanager/pmpages/Pmcalendar.jsx";
const AppRouter = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="services" element={<Services />} />
        <Route path="/generic" element={<GenericPage title="Generic Page" />} />

        <Route path="/set-password" element={<SetPasswordPage />} />

        
        <Route element={<DashboardLayout />}>
          
          <Route path="/user-details" element={<Projectmanager />} />
          
          <Route path="/documents" element={<Documents />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<Settings />} />

          
          <Route path='/projects' element={<Projects />} />
          
          
          <Route path='/backlog/:projectId' element={<BacklogPage />} />
          <Route path='/summary/:projectId' element={<Summary />} />
          <Route path='/list/:projectId' element={<List />} />
          <Route path="/board/:projectId" element={<Board />} />
          <Route path="/timeline/:projectId" element={<Timeline />} />
          <Route path="/calendar/:projectId" element={<Calendar />} />

          
          <Route path='/backlog' element={<Projects />} />

          
          <Route path="/pages/:pageId" element={<PageContent page={{ text: 'Pages', description: 'Create, edit, and collaborate on project documentation.' }} />} />
          <Route path="/code/:pageId" element={<PageContent page={{ text: 'Code', description: 'Browse your repositories and connect your work.' }} />} />
          <Route path="/forms/:pageId" element={<PageContent page={{ text: 'Forms', description: 'Create forms to collect information for your project.' }} />} />
          <Route path="/all-work/:pageId" element={<PageContent page={{ text: 'All work', description: 'View all the work items in your project.' }} />} />
          <Route path="/archived-work-items/:pageId" element={<PageContent page={{ text: 'Archived work items', description: 'Access work items that have been archived.' }} />} />
          <Route path="/deployments/:pageId" element={<PageContent page={{ text: 'Deployments', description: 'Track your deployment pipeline and releases.' }} />} />
          <Route path="/goals/:pageId" element={<PageContent page={{ text: 'Goals', description: "Set and track your team's objectives and key results." }} />} />
          <Route path="/on-call/:pageId" element={<PageContent page={{ text: 'On-call', description: 'Manage on-call schedules and alerts.' }} />} />
          <Route path="/releases/:pageId" element={<PageContent page={{ text: 'Releases', description: 'Track software versions and release cycles.' }} />} />
          <Route path="/reports/:pageId" element={<PageContent page={{ text: 'Reports', description: "Generate reports to analyze your team's progress." }} />} />
          <Route path="/security/:pageId" element={<PageContent page={{ text: 'Security', description: 'Manage security vulnerabilities and compliance.' }} />} />
          <Route path="/shortcuts/:pageId" element={<PageContent page={{ text: 'Shortcuts', description: 'Create quick links to important pages or resources.' }} />} />
        </Route>

        {/* Developer Routes */}
          {/* <Route element={<DeveloperDashboardLayout />}>  */}
            <Route path="/developer/documents" element={<DevDocuments />} />
            <Route path="/developer/notifications" element={<DevNotification />} />
            <Route path="/developer/settings" element={<DevSettings />} /> 

            <Route path="/developer/projects" element={<DeveloperProjects />} />
            <Route path="/developer/backlog/:projectId" element={<DeveloperBacklogPage />} />
            <Route path="/developer/board/:projectId" element={<DevelopersBoard />} />
            <Route path="/developer/calendar/:projectId" element={<DevelopersCalendar />} />
            <Route path="/developer/timeline/:projectId" element={<DevelopersTimeline />} />
            <Route path="/developer/summary/:projectId" element={<DevelopersSummary />} />
            <Route path="/developer/list/:projectId" element={<DevelopersList />} />
            <Route path="/developer/page-content/:projectId" element={<DevelopersPageContent />} />
            <Route path="/developer/dev-user-details" element={<Developerprojectmanager />} />
            <Route path="/developer/dev-user-details/:memberId" element={<DevEditUserModal />} />
        {/* </Route>  */}
        
        
        {/* Tester Routes */}
        <Route path="/tester/projects" element={<TesterProjects />} />

       
        <Route element={<Pmdashboardlayout />}>
          <Route path="/pm/projects" element={<PmProjects />} />
            <Route path="/pm/backlog/:projectId" element={<PmBacklogPage />} />

           <Route path="/pm/documents" element={<PmDocuments />} />
          <Route path="/pm/notifications" element={<PmNotifications />} />
          <Route path="/pm/settings" element={<PmSettings />} />

          <Route path="/pm/summary/:projectId" element={<PmSummary />} />
          <Route path="/pm/list/:projectId" element={<PmList />} />
          <Route path="/pm/board/:projectId" element={<PmBoard />} />
          <Route path="/pm/timeline/:projectId" element={<PmTimeline />} />
          <Route path="/pm/calendar/:projectId" element={<PmCalendar />} />
          <Route path="/pm/user-details" element={<Pmprojectmanager />} />
        </Route>
        
      </Routes>
    </Router>
  );
};

export default AppRouter;