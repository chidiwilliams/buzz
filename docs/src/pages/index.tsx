import React from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import {Redirect} from '@docusaurus/router';

export default function Home(): JSX.Element {
  return (
    <Redirect to="/buzz/docs"></Redirect>
  );
}
