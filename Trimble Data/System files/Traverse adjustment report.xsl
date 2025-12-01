<?xml version='1.0' encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:msxsl="urn:schemas-microsoft-com:xslt" >

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="html" omit-xml-declaration="no"  encoding="utf-8"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="string('.')"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="string(',')"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN="?"
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="string('#0')"/>
<xsl:variable name="DecPl1" select="string(concat('#0', $DecPt, '0'))"/>
<xsl:variable name="DecPl2" select="string(concat('#0', $DecPt, '00'))"/>
<xsl:variable name="DecPl3" select="string(concat('#0', $DecPt, '000'))"/>
<xsl:variable name="DecPl4" select="string(concat('#0', $DecPt, '0000'))"/>
<xsl:variable name="DecPl5" select="string(concat('#0', $DecPt, '00000'))"/>
<xsl:variable name="DecPl6" select="string(concat('#0', $DecPt, '000000'))"/>
<xsl:variable name="DecPl8" select="string(concat('#0', $DecPt, '00000000'))"/>

<xsl:variable name="DegreesSymbol" select="'&#0176;'"/>
<xsl:variable name="MinutesSymbol"><xsl:text>'</xsl:text></xsl:variable>
<xsl:variable name="SecondsSymbol" select="'&quot;'"/>

<xsl:variable name="fileExt" select="'htm'"/>

<xsl:key name="tgtID-search" match="//JOBFile/FieldBook/TargetRecord" use="@ID"/>
<xsl:key name="antennaID-search" match="//JOBFile/FieldBook/AntennaRecord" use="@ID"/>
<xsl:key name="travID-search" match="//JOBFile/FieldBook/TraverseDefinitionRecord" use="@ID"/>

<!-- User variable definitions - Appropriate fields are displayed on the       -->
<!-- Survey Controller screen to allow the user to enter specific values       -->
<!-- which can then be used within the style sheet definition to control the   -->
<!-- output data.                                                              -->
<!--                                                                           -->
<!-- All user variables must be identified by a variable element definition    -->
<!-- named starting with 'userField' (case sensitive) followed by one or more  -->
<!-- characters uniquely identifying the user variable definition.             -->
<!--                                                                           -->
<!-- The text within the 'select' field for the user variable description      -->
<!-- references the actual user variable and uses the '|' character to         -->
<!-- separate the definition details into separate fields as follows:          -->
<!-- For all user variables the first field must be the name of the user       -->
<!-- variable itself (this is case sensitive) and the second field is the      -->
<!-- prompt that will appear on the Survey Controller screen.                  -->
<!-- The third field defines the variable type - there are four possible       -->
<!-- variable types: Double, Integer, String and StringMenu.  These variable   -->
<!-- type references are not case sensitive.                                   -->
<!-- The fields that follow the variable type change according to the type of  -->
<!-- variable as follow:                                                       -->
<!-- Double and Integer: Fourth field = optional minimum value                 -->
<!--                     Fifth field = optional maximum value                  -->
<!--   These minimum and maximum values are used by the Survey Controller for  -->
<!--   entry validation.                                                       -->
<!-- String: No further fields are needed or used.                             -->
<!-- StringMenu: Fourth field = number of menu items                           -->
<!--             Remaining fields are the actual menu items - the number of    -->
<!--             items provided must equal the specified number of menu items. -->
<!--                                                                           -->
<!-- The style sheet must also define the variable itself, named according to  -->
<!-- the definition.  The value within the 'select' field will be displayed in -->
<!-- the Survey Controller as the default value for the item.                  -->

<!-- <xsl:variable name="userField3" select="'IncludeBorders|Include borders in report|stringMenu|2|Yes|No'"/> -->
<xsl:variable name="IncludeBorders" select="'Yes'"/>

<xsl:variable name="Pi" select="3.14159265358979323846264"/>

<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="product">
  <xsl:choose>
    <xsl:when test="JOBFile/@product"><xsl:value-of select="JOBFile/@product"/></xsl:when>
    <xsl:otherwise>Trimble Survey Controller</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="version">
  <xsl:choose>
    <xsl:when test="JOBFile/@productVersion"><xsl:value-of select="JOBFile/@productVersion"/></xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number(JOBFile/@version div 100, $DecPl2, 'Standard')"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <HTML>

  <TITLE>Traverse Report</TITLE>
  <H1>Traverse Report</H1>

  <!-- Set the font size for use in tables -->
  <STYLE TYPE="text/css">
    BODY, TABLE, TD, TH
    {
      font-size:13px;
    }
  </STYLE>

  <HEAD>
  </HEAD>

  <BODY>
    <xsl:call-template name="StartTable"/>
      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Job name:'"/>
        <xsl:with-param name="Val" select="JOBFile/@jobName"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="concat($product, ' version:')"/>
        <xsl:with-param name="Val" select="$version"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Distance units:'"/>
        <xsl:with-param name="Val" select="$DistUnit"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Angle units:'"/>
        <xsl:with-param name="Val" select="$AngleUnit"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Pressure units:'"/>
        <xsl:with-param name="Val" select="$PressUnit"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Temperature units:'"/>
        <xsl:with-param name="Val" select="$TempUnit"/>
      </xsl:call-template>
    <xsl:call-template name="EndTable"/>
    <xsl:call-template name="SeparatingLine"/>

    <!-- Select the FieldBook node to process -->
    <xsl:apply-templates select="JOBFile/FieldBook" />
    
  </BODY>
  </HTML>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">
<!-- Process the records under the FieldBook node in the order encountered -->
  <xsl:for-each select="*">
    <xsl:choose>
      <!-- Handle Traverse Adjustment record -->
      <xsl:when test="name(current()) = 'TraverseAdjustmentRecord'">
      <!-- TraverseAdjustmentRecords can be written out a number of -->
      <!-- times within a file but we are only really interested in -->
      <!-- the one preceding a TraverseClosureRecord -->
      <xsl:if test="name(following-sibling::*[1]) = 'TraverseClosureRecord'">
        <xsl:apply-templates select="current()"/> 
      </xsl:if>

      </xsl:when>

      <!-- Handle Traverse Closure record -->
     <xsl:when test="name(current()) = 'TraverseClosureRecord'">
        <xsl:apply-templates select="current()"/> 
      </xsl:when>

    </xsl:choose>
  </xsl:for-each>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************* Traverse Adjustment Output ***************** -->
<!-- **************************************************************** -->
<xsl:template match="TraverseAdjustmentRecord">

  <xsl:call-template name="StartTable"/>
    <CAPTION align="left">Traverse Adjustment Settings</CAPTION>
    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Adjustment method:'"/>
      <xsl:with-param name="Val">
        <xsl:if test="AdjustmentMethod[.='Transit']">Transit</xsl:if>
        <xsl:if test="AdjustmentMethod[.='Compass']">Compass</xsl:if>
      </xsl:with-param>
    </xsl:call-template>

    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Angular error distribution:'"/>
      <xsl:with-param name="Val">
        <xsl:if test="AngularErrorDistribution[.='ProportionalToDistance']">proportional to distance</xsl:if>
        <xsl:if test="AngularErrorDistribution[.='EqualProportions']">Equal proportions</xsl:if>
        <xsl:if test="AngularErrorDistribution[.='None']">None</xsl:if>
      </xsl:with-param>
    </xsl:call-template>

    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Elevation error distribution:'"/>
      <xsl:with-param name="Val">
        <xsl:if test="ElevationErrorDistribution[.='ProportionalToDistance']">proportional to distance</xsl:if>
        <xsl:if test="ElevationErrorDistribution[.='EqualProportions']">Equal proportions</xsl:if>
        <xsl:if test="ElevationErrorDistribution[.='None']">None</xsl:if>
      </xsl:with-param>
    </xsl:call-template>

  <xsl:call-template name="EndTable"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** Traverse Closure Output ******************* -->
<!-- **************************************************************** -->
<xsl:template match="TraverseClosureRecord">

  <xsl:variable name="TraverseName">
    <xsl:for-each select="key('travID-search', TraverseDefinitionID)">
      <xsl:value-of select="TraverseName"/>
    </xsl:for-each>
  </xsl:variable>

  <xsl:variable name="AdjMethod">
   <xsl:value-of select="preceding-sibling::TraverseAdjustmentRecord[1]/AdjustmentMethod"/>
  </xsl:variable>
  
  <xsl:variable name="travLen" select="TraverseLength"/>
  <xsl:variable name="miscloseDist" select="DistanceMisclose"/>
  <xsl:variable name="miscloseDeltaN" select="DeltaNorth"/>
  <xsl:variable name="miscloseDeltaE" select="DeltaEast"/>
  
  <!-- If the traverse has been adjusted output the traverse details in a 'spreadsheet' table.  -->
  <!-- This record needs to be followed by a TraverseAdjusted PointRecord that is not deleted.  -->
  <!-- This is because a traverse may have been adjusted more than once and if this is the case -->
  <!-- then the original traverse adjusted points are deleted.  Therefore if this is not the    -->
  <!-- final adjustment we don't want to output the traverse 'spreadsheet' details              -->
  <!-- Test the first PointRecord after the current TraverseClosureRecord to ensure it is a     -->
  <!-- non-deleted TraverseAdjusted point.                                                      -->
  <xsl:if test="ClosureStatus[.='Adjusted'] and
                following-sibling::PointRecord[1]/Method[.='TraverseAdjusted'] and
                following-sibling::PointRecord[1]/Deleted[.='false']">
    <xsl:variable name="sumDeltaN">  <!-- Used in Transit adjustment -->
      <xsl:variable name="deltaNs">
        <xsl:for-each select="TraverseLegs/Leg">
          <xsl:variable name="deltaN">
            <xsl:call-template name="CalcDeltaNorth">
              <xsl:with-param name="Azimuth" select="Polar/Azimuth"/>
              <xsl:with-param name="Dist" select="Polar/HorizontalDistance"/>
            </xsl:call-template>
          </xsl:variable>
          <xsl:element name="deltaN">  <!-- Create an element holding the absolute value of the delta N -->
            <xsl:call-template name="Abs">
              <xsl:with-param name="TheValue" select="$deltaN"/>
            </xsl:call-template>
          </xsl:element>
        </xsl:for-each>
      </xsl:variable>
      <xsl:value-of select="sum(msxsl:node-set($deltaNs)/deltaN)"/> <!-- Summ all the deltaN elements in the $deltaNs node set variable -->
    </xsl:variable>

    <xsl:variable name="sumDeltaE">  <!-- Used in Transit adjustment -->
      <xsl:variable name="deltaEs">
        <xsl:for-each select="TraverseLegs/Leg">
          <xsl:variable name="deltaE">
            <xsl:call-template name="CalcDeltaEast">
              <xsl:with-param name="Azimuth" select="Polar/Azimuth"/>
              <xsl:with-param name="Dist" select="Polar/HorizontalDistance"/>
            </xsl:call-template>
          </xsl:variable>
          <xsl:element name="deltaE">  <!-- Create an element holding the absolute value of the delta E -->
            <xsl:call-template name="Abs">
              <xsl:with-param name="TheValue" select="$deltaE"/>
            </xsl:call-template>
          </xsl:element>
        </xsl:for-each>
      </xsl:variable>
      <xsl:value-of select="sum(msxsl:node-set($deltaEs)/deltaE)"/> <!-- Summ all the deltaE elements in the $deltaEs node set variable -->
    </xsl:variable>

    <xsl:call-template name="StartTable"/>
    <CAPTION align="left">
      <xsl:value-of select="concat('Traverse Summary: ', $TraverseName)"/>
    </CAPTION>
    <xsl:call-template name="OutputTableHeaderLine">
      <xsl:with-param name="Hdr1" select="'Point'"/>

      <xsl:with-param name="Hdr2" select="'Adj Azimuth'"/>

      <xsl:with-param name="Hdr3" select="'Measured Hz Dist'"/>

      <xsl:with-param name="Hdr4">
        <xsl:if test="$NECoords = 'true'">Corr N</xsl:if>
        <xsl:if test="$NECoords = 'false'">Corr E</xsl:if>
      </xsl:with-param>

      <xsl:with-param name="Hdr5">
        <xsl:if test="$NECoords = 'true'">Corr E</xsl:if>
        <xsl:if test="$NECoords = 'false'">Corr N</xsl:if>
      </xsl:with-param>

      <xsl:with-param name="Hdr6">
        <xsl:if test="$NECoords = 'true'">Adj North</xsl:if>
        <xsl:if test="$NECoords = 'false'">Adj East</xsl:if>
      </xsl:with-param>

      <xsl:with-param name="Hdr7">
        <xsl:if test="$NECoords = 'true'">Adj East</xsl:if>
        <xsl:if test="$NECoords = 'false'">Adj North</xsl:if>
      </xsl:with-param>
    </xsl:call-template>
    
    <xsl:for-each select="TraverseLegs/Leg">
      <xsl:variable name="FromPt" select="FromPoint"/>
      <xsl:variable name="ToPt" select="ToPoint"/>

      <xsl:if test="position() = 1">  <!-- The first traverse leg -->
        <!-- Get the starting point coordinates from the Reductions section -->
        <xsl:variable name="Coords">
          <xsl:for-each select="/JOBFile/Reductions/Point">
            <xsl:if test="Name = $FromPt">
              <xsl:value-of select="concat(Grid/North, '|', Grid/East)"/>
            </xsl:if>
          </xsl:for-each>
        </xsl:variable>
        <xsl:call-template name="OutputTableLine">
          <xsl:with-param name="Val1" select="FromPoint"/>

          <xsl:with-param name="Val6">
            <xsl:if test="$NECoords = 'true'">
              <xsl:value-of select="format-number(number(substring-before($Coords, '|')) * $DistConvFactor, $DecPl3, 'Standard')"/>
            </xsl:if>
            <xsl:if test="$NECoords = 'false'">
              <xsl:value-of select="format-number(number(substring-after($Coords, '|')) * $DistConvFactor, $DecPl3, 'Standard')"/>
            </xsl:if>
          </xsl:with-param>
          
          <xsl:with-param name="Val7">
            <xsl:if test="$NECoords = 'true'">
              <xsl:value-of select="format-number(number(substring-after($Coords, '|')) * $DistConvFactor, $DecPl3, 'Standard')"/>
            </xsl:if>
            <xsl:if test="$NECoords = 'false'">
              <xsl:value-of select="format-number(number(substring-before($Coords, '|')) * $DistConvFactor, $DecPl3, 'Standard')"/>
            </xsl:if>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:if>

      <!-- Locate the traverse adjusted coordinates for the ToPoint following this closure record -->
      <xsl:variable name="Coords">
        <xsl:choose>
          <xsl:when test="position() != last()">
            <xsl:for-each select="following::PointRecord[Name = $ToPt]">
              <xsl:if test="(Method = 'TraverseAdjusted') and
                            (Deleted = 'false')">
                <xsl:value-of select="concat(Grid/North, '|', Grid/East, '|')"/>
              </xsl:if>
            </xsl:for-each>
          </xsl:when>
          <xsl:otherwise>  <!-- This is the closing point so get coords from Reductions section -->
            <xsl:for-each select="/JOBFile/Reductions/Point">
              <xsl:if test="Name = $ToPt">
                <xsl:value-of select="concat(Grid/North, '|', Grid/East, '|')"/>
              </xsl:if>
            </xsl:for-each>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="Val1" select="ToPoint"/>

        <xsl:with-param name="Val2">
          <xsl:call-template name="FormatAzimuth">
            <xsl:with-param name="TheAzimuth">
              <xsl:value-of select="Polar/Azimuth"/>
            </xsl:with-param>  
          </xsl:call-template>
        </xsl:with-param>

        <xsl:with-param name="Val3" select="format-number(Polar/HorizontalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>

        <!-- Compute the adjustment correction north and east values -->
        <xsl:with-param name="Val4">
          <xsl:if test="$NECoords = 'true'">
            <xsl:variable name="deltaVal">
              <xsl:call-template name="AdjNorthCorrn">
               <xsl:with-param name="adjMethod" select="$AdjMethod"/>
               <xsl:with-param name="azimuth" select="Polar/Azimuth"/>
               <xsl:with-param name="distance" select="Polar/HorizontalDistance"/>
               <xsl:with-param name="totalDist" select="$travLen"/>
               <xsl:with-param name="sumDeltaN" select="$sumDeltaN"/>
               <xsl:with-param name="sumDeltaE" select="$sumDeltaE"/>
               <xsl:with-param name="miscloseDist" select="$miscloseDist"/>
               <xsl:with-param name="miscloseDeltaN" select="$miscloseDeltaN"/>
               <xsl:with-param name="miscloseDeltaE" select="$miscloseDeltaE"/>
              </xsl:call-template>
            </xsl:variable>
            <xsl:value-of select="format-number($deltaVal * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:if>
          <xsl:if test="$NECoords = 'false'">
            <xsl:variable name="deltaVal">
              <xsl:call-template name="AdjEastCorrn">
               <xsl:with-param name="adjMethod" select="$AdjMethod"/>
               <xsl:with-param name="azimuth" select="Polar/Azimuth"/>
               <xsl:with-param name="distance" select="Polar/HorizontalDistance"/>
               <xsl:with-param name="totalDist" select="$travLen"/>
               <xsl:with-param name="sumDeltaN" select="$sumDeltaN"/>
               <xsl:with-param name="sumDeltaE" select="$sumDeltaE"/>
               <xsl:with-param name="miscloseDist" select="$miscloseDist"/>
               <xsl:with-param name="miscloseDeltaN" select="$miscloseDeltaN"/>
               <xsl:with-param name="miscloseDeltaE" select="$miscloseDeltaE"/>
              </xsl:call-template>
            </xsl:variable>
            <xsl:value-of select="format-number($deltaVal * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:if>
        </xsl:with-param>

        <xsl:with-param name="Val5">
          <xsl:if test="$NECoords = 'true'">
            <xsl:variable name="deltaVal">
              <xsl:call-template name="AdjEastCorrn">
               <xsl:with-param name="adjMethod" select="$AdjMethod"/>
               <xsl:with-param name="azimuth" select="Polar/Azimuth"/>
               <xsl:with-param name="distance" select="Polar/HorizontalDistance"/>
               <xsl:with-param name="totalDist" select="$travLen"/>
               <xsl:with-param name="sumDeltaN" select="$sumDeltaN"/>
               <xsl:with-param name="sumDeltaE" select="$sumDeltaE"/>
               <xsl:with-param name="miscloseDist" select="$miscloseDist"/>
               <xsl:with-param name="miscloseDeltaN" select="$miscloseDeltaN"/>
               <xsl:with-param name="miscloseDeltaE" select="$miscloseDeltaE"/>
              </xsl:call-template>
            </xsl:variable>
            <xsl:value-of select="format-number($deltaVal * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:if>
          <xsl:if test="$NECoords = 'false'">
            <xsl:variable name="deltaVal">
              <xsl:call-template name="AdjNorthCorrn">
               <xsl:with-param name="adjMethod" select="$AdjMethod"/>
               <xsl:with-param name="azimuth" select="Polar/Azimuth"/>
               <xsl:with-param name="distance" select="Polar/HorizontalDistance"/>
               <xsl:with-param name="totalDist" select="$travLen"/>
               <xsl:with-param name="sumDeltaN" select="$sumDeltaN"/>
               <xsl:with-param name="sumDeltaE" select="$sumDeltaE"/>
               <xsl:with-param name="miscloseDist" select="$miscloseDist"/>
               <xsl:with-param name="miscloseDeltaN" select="$miscloseDeltaN"/>
               <xsl:with-param name="miscloseDeltaE" select="$miscloseDeltaE"/>
              </xsl:call-template>
            </xsl:variable>
            <xsl:value-of select="format-number($deltaVal * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:if>
        </xsl:with-param>

        <xsl:with-param name="Val6">
          <xsl:if test="$NECoords = 'true'">
            <xsl:value-of select="format-number(number(substring-before($Coords, '|')) * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:if>
          <xsl:if test="$NECoords = 'false'">
            <xsl:variable name="Temp" select="substring-after($Coords, '|')"/>
            <xsl:value-of select="format-number(number(substring-before($Temp, '|')) * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:if>
        </xsl:with-param>
          
        <xsl:with-param name="Val7">
          <xsl:if test="$NECoords = 'true'">
            <xsl:variable name="Temp" select="substring-after($Coords, '|')"/>
            <xsl:value-of select="format-number(number(substring-before($Temp, '|')) * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:if>
          <xsl:if test="$NECoords = 'false'">
            <xsl:value-of select="format-number(number(substring-before($Coords, '|')) * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:if>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:for-each>
    <xsl:call-template name="EndTable"/>
  </xsl:if>

  <!-- Now output the closure details -->
  <xsl:call-template name="StartTable"/>
    <CAPTION align="left">
      <xsl:value-of select="concat('Traverse Closure Details: ', $TraverseName)"/>
    </CAPTION>
    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Adjustment status:'"/>
      <xsl:with-param name="Val">
        <xsl:if test="ClosureStatus[.='NotAdjusted']">Not adjusted</xsl:if>
        <xsl:if test="ClosureStatus[.='Closed']">Closed</xsl:if>
        <xsl:if test="ClosureStatus[.='Adjusted']">
          <xsl:value-of select="concat('Adjusted (', $AdjMethod, ')')"/>
        </xsl:if>
      </xsl:with-param>
    </xsl:call-template>

    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Angular misclose:'"/>
      <xsl:with-param name="Val">
        <xsl:call-template name="FormatAngle">
          <xsl:with-param name="TheAngle">
            <xsl:value-of select="AzimuthMisclose"/>
          </xsl:with-param>  
        </xsl:call-template>
      </xsl:with-param>
    </xsl:call-template>

    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Distance misclose:'"/>
      <xsl:with-param name="Val" select="format-number(DistanceMisclose * $DistConvFactor, $DecPl3, 'Standard')"/>
    </xsl:call-template>

    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Traverse length:'"/>
      <xsl:with-param name="Val" select="format-number(TraverseLength * $DistConvFactor, $DecPl3, 'Standard')"/>
    </xsl:call-template>

    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Precision:'"/>
      <xsl:with-param name="Val" select="concat('1 in ', format-number(Precision, $DecPl1, 'Standard'))"/>
    </xsl:call-template>

    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Delta north:'"/>
      <xsl:with-param name="Val" select="format-number(DeltaNorth * $DistConvFactor, $DecPl3, 'Standard')"/>
    </xsl:call-template>

    <xsl:call-template name="OutputSingleElementTableLine">
      <xsl:with-param name="Hdr" select="'Delta east:'"/>
      <xsl:with-param name="Val" select="format-number(DeltaEast * $DistConvFactor, $DecPl3, 'Standard')"/>
    </xsl:call-template>

    <xsl:if test="DeltaElevation != ''">
      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Delta elevation:'"/>
        <xsl:with-param name="Val" select="format-number(DeltaElevation * $DistConvFactor, $DecPl3, 'Standard')"/>
      </xsl:call-template>
    </xsl:if>

  <xsl:call-template name="EndTable"/>
  <xsl:call-template name="SeparatingLine"/>

</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Compute Adjustment North Correction Line *********** -->
<!-- **************************************************************** -->
<xsl:template name="AdjNorthCorrn">
  <xsl:param name="adjMethod"/>
  <xsl:param name="azimuth"/>
  <xsl:param name="distance"/>
  <xsl:param name="totalDist"/>
  <xsl:param name="sumDeltaN"/>
  <xsl:param name="sumDeltaE"/>
  <xsl:param name="miscloseDist"/>
  <xsl:param name="miscloseDeltaN"/>
  <xsl:param name="miscloseDeltaE"/>

  <xsl:choose>
    <xsl:when test="$adjMethod = 'Compass'">
      <xsl:variable name="adjDist" select="$distance div $totalDist * $miscloseDeltaN"/>
      <xsl:variable name="delta">
        <xsl:call-template name="CalcDeltaNorth">
          <xsl:with-param name="Azimuth" select="$azimuth"/>
          <xsl:with-param name="Dist" select="$adjDist"/>
        </xsl:call-template>
      </xsl:variable>
      <xsl:value-of select="$adjDist * -1"/> <!-- Reverse sign to provide correction rather than delta -->
    </xsl:when>

    <xsl:otherwise>  <!-- Must be Transit adjustment method -->
      <xsl:variable name="absDelta">
        <xsl:call-template name="Abs">
          <xsl:with-param name="TheValue">
            <xsl:call-template name="CalcDeltaNorth">
              <xsl:with-param name="Azimuth" select="$azimuth"/>
              <xsl:with-param name="Dist" select="$distance"/>
            </xsl:call-template>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:variable>
      <xsl:value-of select="$absDelta div $sumDeltaN * $miscloseDeltaN * -1"/>  <!-- Reverse sign to provide correction rather than delta -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Compute Adjustment East Correction Line ************ -->
<!-- **************************************************************** -->
<xsl:template name="AdjEastCorrn">
  <xsl:param name="adjMethod"/>
  <xsl:param name="azimuth"/>
  <xsl:param name="distance"/>
  <xsl:param name="totalDist"/>
  <xsl:param name="sumDeltaN"/>
  <xsl:param name="sumDeltaE"/>
  <xsl:param name="miscloseDist"/>
  <xsl:param name="miscloseDeltaN"/>
  <xsl:param name="miscloseDeltaE"/>

  <xsl:choose>
    <xsl:when test="$adjMethod = 'Compass'">
      <xsl:variable name="adjDist" select="$distance div $totalDist * $miscloseDeltaE"/>
      <xsl:variable name="delta">
        <xsl:call-template name="CalcDeltaEast">
          <xsl:with-param name="Azimuth" select="$azimuth"/>
          <xsl:with-param name="Dist" select="$adjDist"/>
        </xsl:call-template>
      </xsl:variable>
      <xsl:value-of select="$adjDist * -1"/>  <!-- Reverse sign to provide correction rather than delta -->
    </xsl:when>

    <xsl:otherwise>  <!-- Must be Transit adjustment method -->
      <xsl:variable name="absDelta">
        <xsl:call-template name="Abs">
          <xsl:with-param name="TheValue">
            <xsl:call-template name="CalcDeltaEast">
              <xsl:with-param name="Azimuth" select="$azimuth"/>
              <xsl:with-param name="Dist" select="$distance"/>
            </xsl:call-template>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:variable>
      <xsl:value-of select="$absDelta div $sumDeltaE * $miscloseDeltaE * -1"/>  <!-- Reverse sign to provide correction rather than delta -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************ Calc Delta East *********************** -->
<!-- **************************************************************** -->
<xsl:template name="CalcDeltaEast">
  <xsl:param name="Azimuth"/>
  <xsl:param name="Dist"/>

  <xsl:variable name="sineAzimuth">
    <xsl:call-template name="Sine">
      <xsl:with-param name="TheAngle">
        <xsl:call-template name="AngleInRadians">  <!-- Need to use angle in radians -->
          <xsl:with-param name="TheAngle" select="$Azimuth"/>
          <xsl:with-param name="Normalise" select="'False'"/>
        </xsl:call-template>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>
 
  <xsl:value-of select="$Dist * $sineAzimuth"/>

</xsl:template>


<!-- **************************************************************** -->
<!-- *********************** Calc Delta North *********************** -->
<!-- **************************************************************** -->
<xsl:template name="CalcDeltaNorth">
  <xsl:param name="Azimuth"/>
  <xsl:param name="Dist"/>
  
  <xsl:variable name="sineAzimuth">
    <xsl:call-template name="Sine">
      <xsl:with-param name="TheAngle">
        <xsl:call-template name="AngleInRadians">  <!-- Need to use angle in radians -->
          <xsl:with-param name="TheAngle" select="90.0 - $Azimuth"/>
          <xsl:with-param name="Normalise" select="'False'"/>
        </xsl:call-template>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>
 
  <xsl:value-of select="$Dist * $sineAzimuth"/>
    
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** Format a DMS Angle ********************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatDMSAngle">
  <xsl:param name="DecimalAngle"/>
  <xsl:param name="SecDecPlaces" select="0"/>

  <xsl:variable name="Sign">
    <xsl:if test="$DecimalAngle &lt; '0.0'">-1</xsl:if>
    <xsl:if test="$DecimalAngle &gt;= '0.0'">1</xsl:if>
  </xsl:variable>

  <xsl:variable name="PosDecimalDegrees" select="number($DecimalAngle * $Sign)"/>

  <xsl:variable name="PositiveDecimalDegrees">  <!-- Ensure an angle very close to 360° is treated as 0° -->
    <xsl:choose>
      <xsl:when test="(360.0 - $PosDecimalDegrees) &lt; 0.00001">
        <xsl:value-of select="0"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$PosDecimalDegrees"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="decPlFmt">
    <xsl:choose>
      <xsl:when test="$SecDecPlaces = 0"><xsl:value-of select="''"/></xsl:when>
      <xsl:when test="$SecDecPlaces = 1"><xsl:value-of select="'.0'"/></xsl:when>
      <xsl:when test="$SecDecPlaces = 2"><xsl:value-of select="'.00'"/></xsl:when>
      <xsl:when test="$SecDecPlaces = 3"><xsl:value-of select="'.000'"/></xsl:when>
      <xsl:when test="$SecDecPlaces = 4"><xsl:value-of select="'.0000'"/></xsl:when>
      <xsl:when test="$SecDecPlaces = 5"><xsl:value-of select="'.00000'"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="''"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="Degrees" select="floor($PositiveDecimalDegrees)"/>
  <xsl:variable name="DecimalMinutes" select="number(number($PositiveDecimalDegrees - $Degrees) * 60 )"/>
  <xsl:variable name="Minutes" select="floor($DecimalMinutes)"/>
  <xsl:variable name="Seconds" select="number(number($DecimalMinutes - $Minutes)*60)"/>

  <xsl:variable name="PartialyNormalisedMinutes">
    <xsl:if test="format-number($Seconds, concat('00', $decPlFmt)) = '60'"><xsl:value-of select="number($Minutes + 1)"/></xsl:if>
    <xsl:if test="not(format-number($Seconds, concat('00', $decPlFmt)) = '60')"><xsl:value-of select="$Minutes"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="NormalisedSeconds">
    <xsl:if test="format-number($Seconds, concat('00', $decPlFmt)) = '60'"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(format-number($Seconds, concat('00', $decPlFmt)) = '60')"><xsl:value-of select="$Seconds"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="PartialyNormalisedDegrees">
    <xsl:if test="format-number($PartialyNormalisedMinutes, '0') = '60'"><xsl:value-of select="number($Degrees + 1)"/></xsl:if>
    <xsl:if test="not(format-number($PartialyNormalisedMinutes, '0') = '60')"><xsl:value-of select="$Degrees"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="NormalisedDegrees">
    <xsl:if test="format-number($PartialyNormalisedDegrees, '0') = '360'"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(format-number($PartialyNormalisedDegrees, '0') = '360')"><xsl:value-of select="$PartialyNormalisedDegrees"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="NormalisedMinutes">
    <xsl:if test="format-number($PartialyNormalisedMinutes, '00') = '60'"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(format-number($PartialyNormalisedMinutes, '00') = '60')"><xsl:value-of select="$PartialyNormalisedMinutes"/></xsl:if>
  </xsl:variable>

  <xsl:if test="$Sign = -1">-</xsl:if>
  <xsl:value-of select="format-number($NormalisedDegrees, '0')"/>
  <xsl:value-of select="$DegreesSymbol"/>
  <xsl:value-of select="format-number($NormalisedMinutes, '00')"/>
  <xsl:value-of select="$MinutesSymbol"/>
  <xsl:value-of select="format-number($NormalisedSeconds, concat('00', $decPlFmt))"/>
  <xsl:value-of select="$SecondsSymbol"/>
</xsl:template>

<!-- **************************************************************** -->
<!-- ******************* Format a Quadrant Bearing ****************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatQuadrantBearing">
  <xsl:param name="DecimalAngle"/>
  <xsl:param name="SecDecPlaces" select="0"/>

  <xsl:choose>
    <!-- Null azimuth value -->
    <xsl:when test="string(number($DecimalAngle))='NaN'">
      <xsl:value-of select="'?'"/>
    </xsl:when>
    <!-- There is an azimuth value -->
    <xsl:otherwise>
      <xsl:variable name="QuadrantAngle">
        <xsl:if test="($DecimalAngle &lt;= '90.0')">
          <xsl:value-of select="number ( $DecimalAngle )"/>
        </xsl:if>
        <xsl:if test="($DecimalAngle &gt; '90.0') and ($DecimalAngle &lt;= '180.0')">
          <xsl:value-of select="number( 180.0 - $DecimalAngle )"/>
        </xsl:if>
        <xsl:if test="($DecimalAngle &gt; '180.0') and ($DecimalAngle &lt; '270.0')">
          <xsl:value-of select="number( $DecimalAngle - 180.0 )"/>
        </xsl:if>
        <xsl:if test="($DecimalAngle &gt;= '270.0') and ($DecimalAngle &lt;= '360.0')">
          <xsl:value-of select="number( 360.0 - $DecimalAngle )"/>
        </xsl:if>
      </xsl:variable>

      <xsl:variable name="QuadrantPrefix">
        <xsl:if test="($DecimalAngle &lt;= '90.0') or ($DecimalAngle &gt;= '270.0')">
           <xsl:text>N</xsl:text>
        </xsl:if>
        <xsl:if test="($DecimalAngle &gt; '90.0') and ($DecimalAngle &lt; '270.0')">
          <xsl:text>S</xsl:text>
        </xsl:if>
      </xsl:variable>

      <xsl:variable name="QuadrantSuffix">
        <xsl:if test="($DecimalAngle &lt;= '180.0')">
          <xsl:text>E</xsl:text>
        </xsl:if>
        <xsl:if test="($DecimalAngle &gt; '180.0')">
          <xsl:text>W</xsl:text>
        </xsl:if>
      </xsl:variable>

      <xsl:value-of select="$QuadrantPrefix"/>
      <xsl:choose>
        <xsl:when test="$AngleUnit='DMSDegrees'">
          <xsl:call-template name="FormatDMSAngle">
            <xsl:with-param name="DecimalAngle" select="$QuadrantAngle"/>
            <xsl:with-param name="SecDecPlaces" select="$SecDecPlaces"/>
          </xsl:call-template>
        </xsl:when>
        <xsl:otherwise>
          <xsl:call-template name="FormatAngle">
            <xsl:with-param name="TheAngle" select="$QuadrantAngle"/>
            <xsl:with-param name="SecDecPlaces" select="$SecDecPlaces"/>
          </xsl:call-template>
        </xsl:otherwise>
      </xsl:choose>
      <xsl:value-of select="$QuadrantSuffix"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Output Angle in Appropriate Format **************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatAngle">
  <xsl:param name="TheAngle"/>
  <xsl:param name="SecDecPlaces" select="0"/>
  <xsl:param name="DMSOutput" select="'False'"/>

  <xsl:choose>
    <!-- Null angle value -->
    <xsl:when test="string(number($TheAngle))='NaN'">
      <xsl:value-of select="'?'"/>
    </xsl:when>
    <!-- There is an angle value -->
    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="($AngleUnit='DMSDegrees') or not($DMSOutput = 'False')">
          <xsl:call-template name="FormatDMSAngle">
            <xsl:with-param name="DecimalAngle" select="$TheAngle"/>
            <xsl:with-param name="SecDecPlaces" select="$SecDecPlaces"/>
          </xsl:call-template>
        </xsl:when>

        <xsl:when test="($AngleUnit='Gons') and ($DMSOutput = 'False')">
          <xsl:choose>
            <xsl:when test="$SecDecPlaces > 0">  <!-- More accurate angle output required -->
              <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl8, 'Standard')"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl5, 'Standard')"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:when>

        <xsl:when test="($AngleUnit='Mils') and ($DMSOutput = 'False')">
          <xsl:choose>
            <xsl:when test="$SecDecPlaces > 0">  <!-- More accurate angle output required -->
              <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl6, 'Standard')"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl4, 'Standard')"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:when>

        <xsl:when test="($AngleUnit='DecimalDegrees') and ($DMSOutput = 'False')">
          <xsl:choose>
            <xsl:when test="$SecDecPlaces > 0">  <!-- More accurate angle output required -->
              <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl8, 'Standard')"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl5, 'Standard')"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:when>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Output Azimuth in Appropriate Format ************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatAzimuth">
  <xsl:param name="TheAzimuth"/>
  <xsl:param name="SecDecPlaces" select="0"/>
  <xsl:param name="DMSOutput" select="'False'"/>

  <xsl:choose>
    <xsl:when test="//Environment/DisplaySettings/AzimuthFormat = 'QuadrantBearings'">
      <xsl:call-template name="FormatQuadrantBearing">
        <xsl:with-param name="DecimalAngle" select="$TheAzimuth"/>
        <xsl:with-param name="SecDecPlaces" select="$SecDecPlaces"/>
      </xsl:call-template>
    </xsl:when>
    <xsl:otherwise>
      <xsl:call-template name="FormatAngle">
        <xsl:with-param name="TheAngle" select="$TheAzimuth"/>
        <xsl:with-param name="SecDecPlaces" select="$SecDecPlaces"/>
        <xsl:with-param name="DMSOutput" select="$DMSOutput"/>
      </xsl:call-template>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Return the absolute value ******************* -->
<!-- **************************************************************** -->
<xsl:template name="Abs">
  <xsl:param name="TheValue"/>
  <xsl:variable name="Sign">
    <xsl:choose>
      <xsl:when test="$TheValue &lt; '0.0'">
        -1
      </xsl:when>
      <xsl:otherwise>
        1
      </xsl:otherwise>
    </xsl:choose> 
  </xsl:variable>

  <xsl:value-of select="number($Sign * $TheValue)"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Return value raised to specified power ************ -->
<!-- **************************************************************** -->
<xsl:template name="raiseToPower">
  <xsl:param name="number"/>
  <xsl:param name="power"/>
  <xsl:call-template name="raiseToPowerIter">
    <xsl:with-param name="multiplier" select="$number"/>
    <xsl:with-param name="accumulator" select="1"/>
    <xsl:with-param name="reps" select="$power"/>
  </xsl:call-template>
</xsl:template>
  
<xsl:template name="raiseToPowerIter">
  <xsl:param name="multiplier"/>
  <xsl:param name="accumulator"/>
  <xsl:param name="reps"/>
  <xsl:choose>
    <xsl:when test="$reps &gt; 0">
      <xsl:call-template name="raiseToPowerIter">
        <xsl:with-param name="multiplier" select="$multiplier"/>
        <xsl:with-param name="accumulator" select="$accumulator * $multiplier"/>
        <xsl:with-param name="reps" select="$reps - 1"/>
      </xsl:call-template>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$accumulator"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>

  
<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <xsl:choose>
    <xsl:when test="$IncludeBorders != 'Yes'">  <!-- Only include separating lines -->
      <hr></hr>                                 <!-- if there are no table borders -->
    </xsl:when>
    <xsl:otherwise>
      <xsl:call-template name="BlankLine"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************* Output Table Header Line ******************* -->
<!-- **************************************************************** -->
<xsl:template name="OutputTableHeaderLine">
  <xsl:param name="Hdr1" select="''"/>
  <xsl:param name="Hdr2" select="''"/>
  <xsl:param name="Hdr3" select="''"/>
  <xsl:param name="Hdr4" select="''"/>
  <xsl:param name="Hdr5" select="''"/>
  <xsl:param name="Hdr6" select="''"/>
  <xsl:param name="Hdr7" select="''"/>

  <TR>
    <TH width="16%" align="center"><xsl:value-of select="$Hdr1"/></TH>
    <TH width="16%" align="center"><xsl:value-of select="$Hdr2"/></TH>
    <TH width="12%" align="center"><xsl:value-of select="$Hdr3"/></TH>
    <TH width="10%" align="center"><xsl:value-of select="$Hdr4"/></TH>
    <TH width="10%" align="center"><xsl:value-of select="$Hdr5"/></TH>
    <TH width="18%" align="center"><xsl:value-of select="$Hdr6"/></TH>
    <TH width="18%" align="center"><xsl:value-of select="$Hdr7"/></TH>
  </TR>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************ Output Table Line ********************* -->
<!-- **************************************************************** -->
<xsl:template name="OutputTableLine">
  <xsl:param name="Val1" select="''"/>
  <xsl:param name="Val2" select="''"/>
  <xsl:param name="Val3" select="''"/>
  <xsl:param name="Val4" select="''"/>
  <xsl:param name="Val5" select="''"/>
  <xsl:param name="Val6" select="''"/>
  <xsl:param name="Val7" select="''"/>

  <TR>
    <TD width="16%" align="left"><xsl:value-of select="$Val1"/></TD>   <!-- Point name     -->
    <TD width="16%" align="right"><xsl:value-of select="$Val2"/></TD>  <!-- Azimuth        -->
    <TD width="12%" align="right"><xsl:value-of select="$Val3"/></TD>  <!-- Distance       -->
    <TD width="10%" align="right"><xsl:value-of select="$Val4"/></TD>  <!-- Correction N/E -->
    <TD width="10%" align="right"><xsl:value-of select="$Val5"/></TD>  <!-- Correction E/N -->
    <TD width="18%" align="right"><xsl:value-of select="$Val6"/></TD>  <!-- Adjusted N/E   -->
    <TD width="18%" align="right"><xsl:value-of select="$Val7"/></TD>  <!-- Adjusted E/N   -->
  </TR>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ************** Output Single Element Table Line **************** -->
<!-- **************************************************************** -->
<xsl:template name="OutputSingleElementTableLine">
  <xsl:param name="Hdr" select="''"/>
  <xsl:param name="Val" select="''"/>

  <TR>
  <TH width="40%" align="left"><xsl:value-of select="$Hdr"/></TH>
  <TD width="60%" align="left"><xsl:value-of select="$Val"/></TD>
  </TR>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************* Blank Line Output ************************ -->
<!-- **************************************************************** -->
<xsl:template name="BlankLine">
  <xsl:value-of select="string(' ')"/>
  <BR/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************* Start Table ************************** -->
<!-- **************************************************************** -->
<xsl:template name="StartTable">
  <xsl:choose>
    <xsl:when test="$IncludeBorders = 'Yes'">
      <xsl:value-of disable-output-escaping="yes" select="'&lt;TABLE BORDER=1 width=100% cellpadding=2 rules=cols&gt;'"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of disable-output-escaping="yes" select="'&lt;TABLE BORDER=0 width=100% cellpadding=2 rules=cols&gt;'"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************** End Table *************************** -->
<!-- **************************************************************** -->
<xsl:template name="EndTable">
  <xsl:value-of disable-output-escaping="yes" select="'&lt;/TABLE&gt;'"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** Angle in Radians ************************ -->
<!-- **************************************************************** -->
<xsl:template name="AngleInRadians">
  <xsl:param name="TheAngle"/>
  <xsl:param name="Normalise" select="'False'"/>
  <xsl:choose>
    <!-- Null angle value -->
    <xsl:when test="string(number($TheAngle))='NaN'">
      <xsl:value-of select="''"/>
    </xsl:when>
    <!-- There is an angle value -->
    <xsl:otherwise>
      <xsl:variable name="RadiansAngle">
        <xsl:value-of select="$TheAngle * $Pi div 180.0"/>
      </xsl:variable>

      <xsl:variable name="OutAngle">
        <xsl:choose>
          <xsl:when test="$Normalise = 'False'">
            <xsl:value-of select="$RadiansAngle"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:call-template name="AngleBetweenZeroAndTwoPi">
              <xsl:with-param name="AnAngle" select="$RadiansAngle"/>
            </xsl:call-template>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>
      <xsl:value-of select="$OutAngle"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************* Return radians angle less than Two Pi ************ -->
<!-- **************************************************************** -->
<xsl:template name="AngleValueLessThanTwoPi">
  <xsl:param name="InAngle"/>

  <xsl:choose>
    <xsl:when test="$InAngle &gt; $Pi * 2.0">
      <xsl:variable name="NewAngle">
        <xsl:value-of select="$InAngle - $Pi * 2.0"/>
      </xsl:variable>
      <xsl:call-template name="AngleValueLessThanTwoPi">
        <xsl:with-param name="InAngle" select="$NewAngle"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$InAngle"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************* Return radians angle greater than Zero *********** -->
<!-- **************************************************************** -->
<xsl:template name="AngleValueGreaterThanZero">
  <xsl:param name="InAngle"/>

  <xsl:choose>
    <xsl:when test="$InAngle &lt; 0.0">
      <xsl:variable name="NewAngle">
        <xsl:value-of select="$InAngle + $Pi * 2.0"/>
      </xsl:variable>
      <xsl:call-template name="AngleValueGreaterThanZero">
        <xsl:with-param name="InAngle" select="$NewAngle"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$InAngle"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********** Return radians angle between Zero and Two Pi ******** -->
<!-- **************************************************************** -->
<xsl:template name="AngleBetweenZeroAndTwoPi">
  <xsl:param name="AnAngle"/>
  <xsl:variable name="Angle1">
    <xsl:call-template name="AngleValueLessThanTwoPi">
      <xsl:with-param name="InAngle" select="$AnAngle"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="Angle2">
    <xsl:call-template name="AngleValueGreaterThanZero">
      <xsl:with-param name="InAngle" select="$Angle1"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:value-of select="$Angle2"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Return the sine of an angle in radians ************ -->
<!-- **************************************************************** -->
<xsl:template name="Sine">
  <xsl:param name="TheAngle"/>
  <xsl:variable name="NormalisedAngle">
    <xsl:call-template name="AngleBetweenZeroAndTwoPi">
      <xsl:with-param name="AnAngle" select="$TheAngle"/>
    </xsl:call-template>
  </xsl:variable>
  
  <xsl:variable name="TheSine">
    <xsl:call-template name="sineIter">
      <xsl:with-param name="pX2" select="$NormalisedAngle * $NormalisedAngle"/>
      <xsl:with-param name="pRslt" select="$NormalisedAngle"/>
      <xsl:with-param name="pElem" select="$NormalisedAngle"/>
      <xsl:with-param name="pN" select="1"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:value-of select="number($TheSine)"/>
</xsl:template>

<xsl:template name="sineIter">
  <xsl:param name="pX2"/>
  <xsl:param name="pRslt"/>
  <xsl:param name="pElem"/>
  <xsl:param name="pN"/>
  <xsl:param name="pEps" select="0.00000001"/>
  <xsl:variable name="vnextN" select="$pN+2"/>
  <xsl:variable name="vnewElem"  select="-$pElem*$pX2 div ($vnextN*($vnextN - 1))"/>
  <xsl:variable name="vnewResult" select="$pRslt + $vnewElem"/>
  <xsl:variable name="vdiffResult" select="$vnewResult - $pRslt"/>
  <xsl:choose>
    <xsl:when test="$vdiffResult > $pEps or $vdiffResult &lt; -$pEps">
      <xsl:call-template name="sineIter">
        <xsl:with-param name="pX2" select="$pX2"/>
        <xsl:with-param name="pRslt" select="$vnewResult"/>
        <xsl:with-param name="pElem" select="$vnewElem"/>
        <xsl:with-param name="pN" select="$vnextN"/>
        <xsl:with-param name="pEps" select="$pEps"/>
      </xsl:call-template>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$vnewResult"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


</xsl:stylesheet>