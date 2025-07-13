// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
import { getAuth, GoogleAuthProvider } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';

// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyCHcb-fFktRLVATPCHGcOroHcqao7kfnnk",
  authDomain: "enliten-academy.firebaseapp.com",
  projectId: "enliten-academy",
  storageBucket: "enliten-academy.firebasestorage.app",
  messagingSenderId: "744501523528",
  appId: "1:744501523528:web:6ba59cf329995588d6547d",
  measurementId: "G-8E9V9ZL6S1"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);
// Initialize Firebase
export const auth = getAuth(app);
export const db = getFirestore(app);
export const googleProvider = new GoogleAuthProvider();
export default app; 